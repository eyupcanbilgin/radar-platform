"""S-0007 (Kısa vadeli sahip kapitülasyonu: zincir üstü realize kâr/zarar) Ölçüm Motoru.

Kart `docs/hypotheses/S-0007.md` içinde ölçümden ÖNCE dondurulmuştur (commit 37553b5); bu
script o kuralları birebir uygular:

1. Girdi STH-SOPR **günlük** serisidir. `D` gününün değeri `available_at_utc` = D+2 00:00Z'den
   önce hiçbir kararda kullanılamaz (ADR-0050 yayın gecikmesi).
2. `sopr_smooth_days = 3` günlük hareketli ortalama ("sürdürülmüş" realize kâr/zarar).
3. `sopr_dist_days = 30` günlük hareketli **midrank** yüzdelik. Mutlak eşik YOKTUR — özellikle
   `SOPR = 1.0` başabaş noktası kullanılmaz (kart §4.3).
4. LONG `P_sopr <= 20` (sürdürülmüş **zarar**: kırılgan el boşalıyor),
   SHORT `P_sopr >= 80` (sürdürülmüş **kâr**: yükselişe arz salınıyor), arası WAIT.
5. Karar, değerin kullanılabilir olduğu 00:00Z mumunun kapanışında; giriş sonraki saatin
   açılışında; ufuk 24 saat; stop/hedef yok. Günde en çok bir karar.
6. Yön hiçbir fiyat serisinden türetilmez; yalnız zincir üstü realize kâr/zarardan gelir.

İşlem/fold/baseline/kapı mantığı S-0005 motorundan **yeniden kullanılır**, kopyalanmaz: beş
aile aynı protokolle ölçülmeli ki aralarındaki fark hipotezden gelsin, ölçüm farkından değil.

Günlük seride bir sinyal saatlik çerçeveye **tek bir saatte** düşer; diğer 23 saat WAIT'tir.
Bu, sinyali saatlere yaymanın yaratacağı sahte örneklem şişmesini engeller.
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

HYPOTHESIS_ID = "S-0007"
STRATEGY = "S0007OnchainHolderCapitulation"
VALUE_COLUMN = "sthSopr"

# Karttaki dondurulmuş dört serbest parametre. Burada YENİDEN SEÇİLMEZ.
BASE_PARAMETERS: dict[str, int | float] = {
    "sopr_smooth_days": 3,
    "sopr_dist_days": 30,
    "upper_percentile": 80,
    "lower_percentile": 20,
}


def load_onchain_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Günlük on-chain seriyi ve saatlik işlem enstrümanını ayrı ayrı getir.

    İkisi bilinçli olarak **ayrı** kalır: on-chain değer günlüktür ve saatlere yayılırsa aynı
    bilgi 24 kez işlem üretir. Birleştirme yalnız karar saatinde yapılır.
    """
    sopr_path = market_data_root() / "onchain" / "bitcoin-data" / "STH_SOPR-1d.feather"
    perp_path = data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    for path in (sopr_path, perp_path):
        if not path.exists():
            raise FileNotFoundError(f"Gerekli veri dosyası bulunamadı: {path}")

    daily = pd.read_feather(sopr_path)
    for column in ("available_at_utc", VALUE_COLUMN):
        if column not in daily.columns:
            raise ValueError(f"{sopr_path.name}: '{column}' kolonu yok")
    daily["available_at_utc"] = pd.to_datetime(daily["available_at_utc"], utc=True)
    daily = daily.sort_values("available_at_utc").reset_index(drop=True)

    perp = pd.read_feather(perp_path)
    perp["date_dt"] = pd.to_datetime(perp["date"], utc=True)
    perp = (
        perp[["date_dt", "open", "close"]]
        .rename(columns={"open": "perp_open", "close": "perp_close"})
        .sort_values("date_dt")
        .reset_index(drop=True)
    )
    if daily.empty or perp.empty:
        raise ValueError("On-chain veya perp serisi boş")
    return daily, perp


def compute_s0007_signals(
    daily: pd.DataFrame,
    perp: pd.DataFrame,
    *,
    sopr_smooth_days: int,
    sopr_dist_days: int,
    upper_percentile: float,
    lower_percentile: float,
) -> pd.DataFrame:
    """Kart §4.2–4.5: yumuşat, göreli yüzdeliğe çevir, bandı uygula, karar saatine yerleştir."""
    smooth_bars = int(sopr_smooth_days)
    dist_bars = int(sopr_dist_days)

    d = daily.copy()
    d["sopr_smooth"] = d[VALUE_COLUMN].rolling(window=smooth_bars, min_periods=smooth_bars).mean()
    d["sopr_pct_rank"] = (
        d["sopr_smooth"]
        .rolling(window=dist_bars, min_periods=max(1, dist_bars // 2))
        .apply(_midrank_percentile, raw=True)
    )

    # Yön: sürdürülmüş ZARAR long, sürdürülmüş KÂR short (kart §4.4, dondurulmuş).
    cond_long = d["sopr_pct_rank"] <= lower_percentile
    cond_short = d["sopr_pct_rank"] >= upper_percentile
    d["daily_signal"] = np.select([cond_long, cond_short], [1, -1], default=0)
    # NaN yüzdelikte sinyal üretilmez: bilinmeyen "nötr" değildir.
    d.loc[d["sopr_pct_rank"].isna(), "daily_signal"] = 0

    frame = perp.merge(
        d[["available_at_utc", "daily_signal", "sopr_pct_rank"]],
        left_on="date_dt",
        right_on="available_at_utc",
        how="left",
    )
    # Karar yalnız değerin KULLANILABİLİR OLDUĞU saatte doğar; kalan 23 saat WAIT'tir.
    frame["signal"] = frame["daily_signal"].fillna(0).astype(int)
    frame = frame.drop(columns=["daily_signal"]).reset_index(drop=True)

    perp_open = frame["perp_open"].values
    perp_close = frame["perp_close"].values
    forward = np.full(len(frame), np.nan, dtype=float)
    for index in range(len(frame) - HORIZON_HOURS):
        entry = perp_open[index + 1]
        if entry > 0:
            forward[index] = (perp_close[index + HORIZON_HOURS] - entry) / entry
    frame["fwd_24h_raw"] = forward
    return frame


def _run_configuration(daily, perp, plan: dict, fee: dict, parameters: dict) -> dict:
    signals = compute_s0007_signals(
        daily,
        perp,
        sopr_smooth_days=int(parameters["sopr_smooth_days"]),
        sopr_dist_days=int(parameters["sopr_dist_days"]),
        upper_percentile=float(parameters["upper_percentile"]),
        lower_percentile=float(parameters["lower_percentile"]),
    )
    trades = _collect_trades(signals, plan, fee)
    trades["signals_frame"] = signals
    trades["cumulative"] = {
        scenario: _cumulative(values) for scenario, values in trades["net_by_scenario"].items()
    }
    return trades


def run_s0007_evaluation(registry_path: Path | None = None) -> dict:
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

    daily, perp = load_onchain_frames()
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        horizon_hours=HORIZON_HOURS,
        allow_locked_oos=False,
        config=protocol,
    )

    base = _run_configuration(daily, perp, plan, fee, BASE_PARAMETERS)
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
        daily=daily,
        perp=perp,
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
    *, daily, perp, plan, fee, base, gates_cfg, registry_path, base_rejected: bool
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
        result = _run_configuration(daily, perp, plan, fee, parameters)
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
    print(json.dumps(run_s0007_evaluation(), indent=2, ensure_ascii=False, default=float))
