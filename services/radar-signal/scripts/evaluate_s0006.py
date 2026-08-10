"""S-0006 (Katılım Kompozisyonu: spot vs perp hacim payı) Ölçüm Motoru.

Kart `docs/hypotheses/S-0006.md` içinde ölçümden ÖNCE dondurulmuştur; bu script o kuralları
birebir uygular:

1. `spot_share = spot_volume / (spot_volume + perp_volume)`; payda ≤ 0 olan saat DÜŞÜRÜLÜR
   ("pay %50'ydi" sayılmaz).
2. 8 saatlik hareketli ortalama.
3. 30 günlük (720 saat) hareketli **midrank** yüzdelik; mutlak pay eşiği kullanılmaz.
4. LONG >= 80 (spot öncülüğü), SHORT <= 20 (kaldıraç öncülüğü), arası WAIT.
5. Karar saat kapanışında, giriş sonraki açılışta, ufuk 24 saat, stop/hedef yok.
6. Yön hiçbir fiyat serisinden türetilmez; yalnız hacim bileşiminden gelir.

İşlem/fold/baseline/kapı mantığı S-0005 motorundan **yeniden kullanılır**, kopyalanmaz:
iki aile aynı protokolle ölçülmeli ki aralarındaki fark hipotezden gelsin, ölçüm
farkından değil.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.baseline_evaluator import evaluate_plan_baselines
from scripts.costslib import effective_fee, load_costs
from scripts.datapaths import data_dir, market_data_root, verify_manifest
from scripts.evaluate_s0005 import (
    HORIZON_HOURS,
    MIN_TRADES,
    _baseline_cumulative,
    _collect_trades,
    _cumulative,
    _midrank_percentile,
)
from scripts.provenance import environment_fingerprint
from scripts.pulse_stats import moving_block_test
from scripts.registrylib import (
    git_commit_hash,
    latest_manifest_hash,
    read_all,
    record_run,
)
from scripts.statistical_gates import (
    StatisticalGateError,
    build_sensitivity_plan,
    evaluate_dsr_gate,
    evaluate_pbo_cscv,
    evaluate_sensitivity,
)
from scripts.walk_forward_lib import (
    generate_walk_forward_plan,
    load_research_protocol_config,
)

HYPOTHESIS_ID = "S-0006"
STRATEGY = "S0006ParticipationComposition"

# Karttaki dondurulmuş dört serbest parametre. Burada YENİDEN SEÇİLMEZ.
BASE_PARAMETERS: dict[str, int | float] = {
    "share_smooth_hours": 8,
    "share_dist_days": 30,
    "upper_percentile": 80,
    "lower_percentile": 20,
}


def load_participation_frame() -> pd.DataFrame:
    """Spot hacmi, perp hacmi ve işlem enstrümanını tek saatlik çerçevede birleştir."""
    spot_path = market_data_root() / "binance" / "spot" / "BTC_USDT-1h-spot.feather"
    perp_path = data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    for path in (spot_path, perp_path):
        if not path.exists():
            raise FileNotFoundError(f"Gerekli veri dosyası bulunamadı: {path}")

    spot = pd.read_feather(spot_path)
    spot["date_dt"] = pd.to_datetime(spot["date"], utc=True)
    spot = spot[["date_dt", "volume"]].rename(columns={"volume": "spot_volume"})

    perp = pd.read_feather(perp_path)
    perp["date_dt"] = pd.to_datetime(perp["date"], utc=True)
    perp = perp[["date_dt", "open", "close", "volume"]].rename(
        columns={"open": "perp_open", "close": "perp_close", "volume": "perp_volume"}
    )

    merged = spot.merge(perp, on="date_dt", how="inner").sort_values("date_dt")
    merged = merged.reset_index(drop=True)
    if merged.empty:
        raise ValueError("Spot ve perp serilerinin kesişimi boş")

    total = merged["spot_volume"] + merged["perp_volume"]
    # Payda ≤ 0 olan saat düşürülür; "pay %50'ydi" varsayımı yapılmaz (fail-closed).
    merged = merged[total > 0].reset_index(drop=True)
    merged["spot_share"] = merged["spot_volume"] / (merged["spot_volume"] + merged["perp_volume"])
    return merged


def compute_s0006_signals(
    frame: pd.DataFrame,
    *,
    share_smooth_hours: int,
    share_dist_days: int,
    upper_percentile: float,
    lower_percentile: float,
) -> pd.DataFrame:
    """Kart §4.2–4.4: yumuşat, göreli yüzdeliğe çevir, bandı uygula."""
    df = frame.copy()
    smooth_bars = int(share_smooth_hours)
    dist_bars = int(share_dist_days) * 24

    df["share_smooth"] = (
        df["spot_share"].rolling(window=smooth_bars, min_periods=smooth_bars).mean()
    )
    df["share_pct_rank"] = (
        df["share_smooth"]
        .rolling(window=dist_bars, min_periods=dist_bars // 2)
        .apply(_midrank_percentile, raw=True)
    )

    cond_long = df["share_pct_rank"] >= upper_percentile
    cond_short = df["share_pct_rank"] <= lower_percentile
    df["signal"] = np.select([cond_long, cond_short], [1, -1], default=0)
    # NaN yüzdelikte sinyal üretilmez: bilinmeyen "nötr" değildir.
    df.loc[df["share_pct_rank"].isna(), "signal"] = 0

    perp_open = df["perp_open"].values
    perp_close = df["perp_close"].values
    forward = np.full(len(df), np.nan, dtype=float)
    for index in range(len(df) - HORIZON_HOURS):
        entry = perp_open[index + 1]
        if entry > 0:
            forward[index] = (perp_close[index + HORIZON_HOURS] - entry) / entry
    df["fwd_24h_raw"] = forward
    return df


def _run_configuration(frame: pd.DataFrame, plan: dict, fee: dict, parameters: dict) -> dict:
    signals = compute_s0006_signals(
        frame,
        share_smooth_hours=int(parameters["share_smooth_hours"]),
        share_dist_days=int(parameters["share_dist_days"]),
        upper_percentile=float(parameters["upper_percentile"]),
        lower_percentile=float(parameters["lower_percentile"]),
    )
    trades = _collect_trades(signals, plan, fee)
    trades["signals_frame"] = signals
    trades["cumulative"] = {
        scenario: _cumulative(values) for scenario, values in trades["net_by_scenario"].items()
    }
    return trades


def run_s0006_evaluation(registry_path: Path | None = None) -> dict:
    manifest = verify_manifest()
    if manifest.get("status") != "ok":
        raise ValueError(f"Veri manifest doğrulaması başarısız: {manifest}")

    protocol = load_research_protocol_config()
    gates_cfg = protocol["statistical_gates"]
    costs = load_costs()
    fee = {
        "realistic": effective_fee(costs, "realistic"),
        "taker_heavy": effective_fee(costs, "taker_heavy"),
    }

    frame = load_participation_frame()
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        horizon_hours=HORIZON_HOURS,
        allow_locked_oos=False,
        config=protocol,
    )

    base = _run_configuration(frame, plan, fee, BASE_PARAMETERS)
    total_trades = len(base["raw_returns"])

    if total_trades < MIN_TRADES:
        return _finalize(
            {
                "hypothesis_id": HYPOTHESIS_ID,
                "strategy": STRATEGY,
                "total_trades": total_trades,
                "verdict": f"invalid (insufficient sample: {total_trades} < {MIN_TRADES} trades)",
                "rejection_reasons": [],
            },
            registry_path,
            fee["realistic"],
        )

    candle_records = pd.read_feather(
        data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    ).to_dict(orient="records")
    baselines = {
        scenario: evaluate_plan_baselines(
            plan=plan, candles=candle_records, costs=costs, scenario=scenario
        )
        for scenario in ("realistic", "taker_heavy")
    }

    rng = np.random.default_rng(42)
    long_share = float(np.mean([1 if value == 1 else 0 for value in base["signals"]]))
    p_value = float(
        moving_block_test(
            signal_values=np.array(base["raw_returns"]) * 10000.0,
            base=base["signals_frame"]["fwd_24h_raw"].dropna().values * 10000.0,
            long_share=long_share,
            n_bootstrap=2000,
            rng=rng,
            mode="directional",
            block_size=HORIZON_HOURS,
        ).get("p_greater", 1.0)
    )

    fold_ratio = (
        base["positive_folds"]["realistic"] / base["valid_folds"] if base["valid_folds"] else 0.0
    )

    reasons: list[str] = []
    for scenario in ("realistic", "taker_heavy"):
        if base["cumulative"][scenario] <= 0:
            reasons.append(f"{scenario} net_return <= 0")
        for baseline_name in ("buy_and_hold", "simple_trend"):
            if base["cumulative"][scenario] <= _baseline_cumulative(
                baselines[scenario], baseline_name
            ):
                reasons.append(f"failed to beat {scenario} {baseline_name} baseline")
    if p_value >= 0.05:
        reasons.append(f"bootstrap p-value {p_value:.4f} >= 0.05")
    min_fold_ratio = gates_cfg["min_positive_fold_ratio"]
    if fold_ratio < min_fold_ratio:
        reasons.append(f"fold consistency {fold_ratio:.1%} < {min_fold_ratio:.0%}")

    gates = _run_extra_gates(
        frame=frame,
        plan=plan,
        fee=fee,
        base=base,
        gates_cfg=gates_cfg,
        registry_path=registry_path,
        base_rejected=bool(reasons),
    )
    reasons.extend(gates["failures"])

    verdict = f"rejected ({'; '.join(reasons)})" if reasons else "accepted (Development level)"
    summary = {
        "hypothesis_id": HYPOTHESIS_ID,
        "strategy": STRATEGY,
        "timerange": "2024-01-01T00:00:00Z -> 2026-08-04T00:00:00Z",
        "frozen_parameters": BASE_PARAMETERS,
        "total_trades": total_trades,
        "valid_folds_count": base["valid_folds"],
        "fold_positive_ratio": fold_ratio,
        "bootstrap_p_value": p_value,
        "performance": {
            scenario: {
                "cum_net_return": base["cumulative"][scenario],
                "avg_net_return": float(np.mean(base["net_by_scenario"][scenario]))
                if base["net_by_scenario"][scenario]
                else 0.0,
                "baseline_bnh_return": _baseline_cumulative(baselines[scenario], "buy_and_hold"),
                "baseline_trend_return": _baseline_cumulative(baselines[scenario], "simple_trend"),
            }
            for scenario in ("realistic", "taker_heavy")
        },
        "statistical_gates": gates["report"],
        "verdict": verdict,
        "rejection_reasons": reasons,
    }
    return _finalize(summary, registry_path, fee["realistic"])


def _run_extra_gates(
    *, frame, plan, fee, base, gates_cfg, registry_path, base_rejected: bool
) -> dict:
    plan_variants = build_sensitivity_plan(
        BASE_PARAMETERS, relative_delta=gates_cfg["sensitivity"]["relative_delta"]
    )
    if base_rejected:
        return {
            "failures": [],
            "report": {
                "status": "not_evaluated",
                "reason": "base hypothesis rejected before extra gates; retention undefined",
                "planned_variants": [item["variant_id"] for item in plan_variants],
            },
        }

    variant_returns: dict[str, list[float]] = {}
    variant_metrics: dict[str, dict[str, float]] = {}
    for variant in plan_variants:
        parameters = dict(BASE_PARAMETERS)
        parameters[variant["parameter"]] = variant["varied_value"]
        result = _run_configuration(frame, plan, fee, parameters)
        variant_returns[variant["variant_id"]] = result["net_by_scenario"]["realistic"]
        variant_metrics[variant["variant_id"]] = result["cumulative"]

    registry_trials = (
        len(
            {
                row.get("hypothesis_id")
                for row in read_all(registry_path)
                if row.get("hypothesis_id", "").startswith("S-")
            }
        )
        + 1
    )

    failures: list[str] = []
    report: dict = {"status": "evaluated", "registry_trial_count": registry_trials}

    dsr = evaluate_dsr_gate(
        returns_by_trial={"candidate": base["net_by_scenario"]["realistic"], **variant_returns},
        observed_trial_id="candidate",
        registry_trial_count=registry_trials,
        confidence_threshold=gates_cfg["dsr"]["confidence_threshold"],
    )
    report["dsr"] = dsr
    if dsr.get("status") != "passed":
        failures.append(f"DSR gate failed (probability {dsr.get('dsr_probability')})")

    pbo = evaluate_pbo_cscv(
        returns_by_configuration={
            "candidate": base["net_by_scenario"]["realistic"],
            **variant_returns,
        },
        partitions=gates_cfg["pbo_cscv"]["partitions"],
        max_combinations=gates_cfg["pbo_cscv"]["max_combinations"],
        rejection_threshold=gates_cfg["pbo_cscv"]["rejection_threshold"],
    )
    report["pbo_cscv"] = pbo
    if pbo.get("status") != "passed":
        failures.append(f"PBO/CSCV gate failed (pbo {pbo.get('pbo')})")

    try:
        sensitivity = evaluate_sensitivity(
            base_metrics=base["cumulative"],
            variant_metrics=variant_metrics,
            expected_variant_ids=[item["variant_id"] for item in plan_variants],
            required_scenarios=["realistic", "taker_heavy"],
            min_retention_ratio=gates_cfg["sensitivity"]["min_performance_retention_ratio"],
        )
    except StatisticalGateError as error:
        sensitivity = {"status": "not_evaluated", "reason": str(error)}
    report["sensitivity"] = sensitivity
    if sensitivity.get("status") == "failed":
        failures.append(f"±20% sensitivity failed: {sensitivity['failures']}")

    report["period_groups"] = {
        scenario: len(groups) for scenario, groups in base["period_returns"].items()
    }
    return {"failures": failures, "report": report}


def _finalize(summary: dict, registry_path: Path | None, fee_realistic: float) -> dict:
    existing = [
        row
        for row in read_all(registry_path)
        if row.get("hypothesis_id") == HYPOTHESIS_ID
        and row.get("strategy_version") == git_commit_hash()
        and row.get("dataset_snapshot") == latest_manifest_hash()
        and not row.get("verdict", "").startswith("invalid")
    ]
    entry = (
        existing[0]
        if existing
        else record_run(
            registry_path=registry_path,
            hypothesis_id=HYPOTHESIS_ID,
            strategy=STRATEGY,
            scenario="realistic_and_taker_heavy",
            effective_fee=fee_realistic,
            exit_code=0,
            verdict=summary["verdict"],
            result=summary,
            pairs=["BTC/USDT:USDT"],
            created_by="claude",
        )
    )
    summary["registry_experiment_id"] = entry["experiment_id"]
    summary["provenance"] = environment_fingerprint()
    return summary


if __name__ == "__main__":
    print(json.dumps(run_s0006_evaluation(), indent=2, ensure_ascii=False, default=float))
