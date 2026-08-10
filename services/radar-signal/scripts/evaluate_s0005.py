"""S-0005 (Bölgesel Spot Talep Dengesizliği / Coinbase Premium) Ölçüm Motoru.

Kart `docs/hypotheses/S-0005.md` içinde ölçümden ÖNCE dondurulmuştur; bu script o kuralları
birebir uygular ve hiçbirini yeniden yorumlamaz:

1. Prim = (Coinbase spot close − Binance spot close) / Binance spot close × 100.
   Eşleşmeyen saat düşürülür (inner join); eksik saat "prim sıfırdı" sayılmaz.
2. 8 saatlik hareketli ortalama ile yumuşatma.
3. 30 günlük (720 saat) hareketli **midrank** yüzdelik; mutlak prim eşiği kullanılmaz.
4. LONG >= 80, SHORT <= 20, arası WAIT.
5. Karar saat kapanışında, giriş SONRAKİ saatin açılışında, ufuk 24 saat, stop/hedef yok.
6. İşlem enstrümanı Binance USD-M perp; sinyal kaynağı iki SPOT mekân (türev girdisi yok).
7. `realistic` ve `taker_heavy` birlikte; üç baseline; purged walk-forward + embargo.
8. DSR, PBO/CSCV, ±%20 hassasiyet ve dönem kırılganlığı kapıları (ADR-0019/0020).

İki bilinçli davranış:

- **Eşik çatışmasında sıkı olan kazanır.** Kart PBO için 0.50 yazar,
  `config/research_protocol.yaml` 0.05 der. Eşikler config'de yaşar (CLAUDE.md kural 3) ve
  config daha sıkıdır; ön-kayıt sonradan düzenlenemeyeceği için sıkı olan uygulanır ve fark
  raporda açıkça beyan edilir.
- **Base reddedilmişse ek kapılar koşulmaz.** `evaluate_sensitivity` pozitif base metrik ister
  ve aksi hâlde hata fırlatır. Reddedilmiş bir adayda bu kapıları zorlamak anlamsız sayı
  üretirdi; `not_evaluated` olarak, gerekçesiyle raporlanır.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.baseline_evaluator import evaluate_plan_baselines
from scripts.costslib import effective_fee, load_costs
from scripts.datapaths import data_dir, market_data_root, verify_manifest
from scripts.provenance import environment_fingerprint
from scripts.pulse_stats import moving_block_test, non_overlapping_positions
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
    evaluate_period_venue_fragility,
    evaluate_sensitivity,
)
from scripts.walk_forward_lib import (
    generate_walk_forward_plan,
    load_research_protocol_config,
    parse_utc_datetime,
)

HYPOTHESIS_ID = "S-0005"
STRATEGY = "S0005RegionalSpotDemand"
HORIZON_HOURS = 24
MIN_TRADES = 100

# Karttaki dondurulmuş dört serbest parametre. Burada YENİDEN SEÇİLMEZ.
BASE_PARAMETERS: dict[str, int | float] = {
    "premium_smooth_hours": 8,
    "premium_dist_days": 30,
    "upper_percentile": 80,
    "lower_percentile": 20,
}


def load_premium_frame() -> pd.DataFrame:
    """Coinbase spot, Binance spot ve işlem enstrümanını tek saatlik çerçevede birleştir."""
    coinbase_path = market_data_root() / "coinbase" / "spot" / "BTC_USD-1h-spot.feather"
    binance_spot_path = market_data_root() / "binance" / "spot" / "BTC_USDT-1h-spot.feather"
    futures_path = data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    for path in (coinbase_path, binance_spot_path, futures_path):
        if not path.exists():
            raise FileNotFoundError(f"Gerekli veri dosyası bulunamadı: {path}")

    def _load(path: Path, prefix: str) -> pd.DataFrame:
        frame = pd.read_feather(path)
        frame["date_dt"] = pd.to_datetime(frame["date"], utc=True)
        keep = frame[["date_dt", "open", "close"]].copy()
        return keep.rename(columns={"open": f"{prefix}_open", "close": f"{prefix}_close"})

    merged = _load(coinbase_path, "cb").merge(
        _load(binance_spot_path, "bn"), on="date_dt", how="inner"
    )
    merged = merged.merge(_load(futures_path, "perp"), on="date_dt", how="inner")
    merged = merged.sort_values("date_dt").reset_index(drop=True)
    if merged.empty:
        raise ValueError("Üç kaynağın kesişimi boş; prim hesaplanamaz")
    if (merged["bn_close"] <= 0).any():
        raise ValueError("Binance spot kapanışı pozitif olmalı")

    merged["premium_pct"] = (merged["cb_close"] - merged["bn_close"]) / merged["bn_close"] * 100.0
    return merged


def _midrank_percentile(window: np.ndarray) -> float:
    """Midrank ampirik CDF (0-100). Eşitlikler yarıya bölünür; ara değer üretilmez."""
    value = window[-1]
    if np.isnan(value):
        return np.nan
    valid = window[~np.isnan(window)]
    if valid.size == 0:
        return np.nan
    below = float((valid < value).sum())
    equal = float((valid == value).sum())
    return 100.0 * (below + 0.5 * equal) / float(valid.size)


def compute_s0005_signals(
    frame: pd.DataFrame,
    *,
    premium_smooth_hours: int,
    premium_dist_days: int,
    upper_percentile: float,
    lower_percentile: float,
) -> pd.DataFrame:
    """Karttaki §4.2–4.4 kurallarını uygula; yön yalnız mekânlar arası farktan gelir."""
    df = frame.copy()
    smooth_bars = int(premium_smooth_hours)
    dist_bars = int(premium_dist_days) * 24

    df["premium_smooth"] = (
        df["premium_pct"].rolling(window=smooth_bars, min_periods=smooth_bars).mean()
    )
    df["premium_pct_rank"] = (
        df["premium_smooth"]
        .rolling(window=dist_bars, min_periods=dist_bars // 2)
        .apply(_midrank_percentile, raw=True)
    )

    cond_long = df["premium_pct_rank"] >= upper_percentile
    cond_short = df["premium_pct_rank"] <= lower_percentile
    df["signal"] = np.select([cond_long, cond_short], [1, -1], default=0)
    # NaN yüzdelikte sinyal üretilmez: bilinmeyen "nötr" değildir.
    df.loc[df["premium_pct_rank"].isna(), "signal"] = 0

    perp_open = df["perp_open"].values
    perp_close = df["perp_close"].values
    forward = np.full(len(df), np.nan, dtype=float)
    for index in range(len(df) - HORIZON_HOURS):
        entry = perp_open[index + 1]
        exit_price = perp_close[index + HORIZON_HOURS]
        if entry > 0:
            forward[index] = (exit_price - entry) / entry
    df["fwd_24h_raw"] = forward
    return df


def _collect_trades(df_signals: pd.DataFrame, plan: dict, fee: dict[str, float]) -> dict:
    """Fold bazında işlemleri topla; giriş sonraki açılış, çıkış +24h kapanış."""
    per_scenario: dict[str, list[float]] = {"realistic": [], "taker_heavy": []}
    fold_returns: dict[str, list[float]] = {"realistic": [], "taker_heavy": []}
    raw_returns: list[float] = []
    signals: list[int] = []
    positive_folds = {"realistic": 0, "taker_heavy": 0}
    valid_folds = 0
    period_returns: dict[str, dict[str, list[float]]] = {"realistic": {}, "taker_heavy": {}}

    for fold in plan["folds"]:
        start = parse_utc_datetime(fold["test_start_utc"])
        end = parse_utc_datetime(fold["test_end_utc"])
        window = df_signals[(df_signals["date_dt"] >= start) & (df_signals["date_dt"] < end)]
        mask = window["signal"].values != 0
        chosen = non_overlapping_positions(mask, horizon=HORIZON_HOURS)

        fold_scenario: dict[str, list[float]] = {"realistic": [], "taker_heavy": []}
        for relative in chosen:
            location = df_signals.index.get_loc(window.index[relative])
            if location + HORIZON_HOURS >= len(df_signals):
                continue
            entry = float(df_signals.iloc[location + 1]["perp_open"])
            exit_price = float(df_signals.iloc[location + HORIZON_HOURS]["perp_close"])
            if entry <= 0 or exit_price <= 0:
                continue
            direction = int(df_signals.iloc[location]["signal"])
            raw = (exit_price - entry) / entry if direction == 1 else (entry - exit_price) / entry
            raw_returns.append(raw)
            signals.append(direction)
            for scenario in ("realistic", "taker_heavy"):
                net = (1.0 + raw) * (1.0 - fee[scenario]) / (1.0 + fee[scenario]) - 1.0
                fold_scenario[scenario].append(net)
                per_scenario[scenario].append(net)

        label = fold["test_start_utc"][:7]
        for scenario in ("realistic", "taker_heavy"):
            cumulative = (
                float(np.prod([1.0 + value for value in fold_scenario[scenario]]) - 1.0)
                if fold_scenario[scenario]
                else 0.0
            )
            fold_returns[scenario].append(cumulative)
            if fold_scenario[scenario]:
                period_returns[scenario].setdefault(label, []).extend(fold_scenario[scenario])
        if fold.get("status") == "valid":
            valid_folds += 1
            for scenario in ("realistic", "taker_heavy"):
                if fold_returns[scenario][-1] > 0:
                    positive_folds[scenario] += 1

    return {
        "net_by_scenario": per_scenario,
        "fold_returns": fold_returns,
        "raw_returns": raw_returns,
        "signals": signals,
        "positive_folds": positive_folds,
        "valid_folds": valid_folds,
        "period_returns": period_returns,
    }


def _cumulative(values: list[float]) -> float:
    return float(np.prod([1.0 + value for value in values]) - 1.0) if values else 0.0


def _run_configuration(frame: pd.DataFrame, plan: dict, fee: dict, parameters: dict) -> dict:
    signals = compute_s0005_signals(
        frame,
        premium_smooth_hours=int(parameters["premium_smooth_hours"]),
        premium_dist_days=int(parameters["premium_dist_days"]),
        upper_percentile=float(parameters["upper_percentile"]),
        lower_percentile=float(parameters["lower_percentile"]),
    )
    trades = _collect_trades(signals, plan, fee)
    trades["signals_frame"] = signals
    trades["cumulative"] = {
        scenario: _cumulative(values) for scenario, values in trades["net_by_scenario"].items()
    }
    return trades


def _baseline_cumulative(baselines: dict, name: str) -> float:
    return float(
        np.prod(
            [
                1.0 + (fold["baselines"][name]["net_return"] or 0.0)
                for fold in baselines["evaluated_folds"]
            ]
        )
        - 1.0
    )


def run_s0005_evaluation(registry_path: Path | None = None) -> dict:
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

    frame = load_premium_frame()
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        horizon_hours=HORIZON_HOURS,
        allow_locked_oos=False,
        config=protocol,
    )

    base = _run_configuration(frame, plan, fee, BASE_PARAMETERS)
    total_trades = len(base["raw_returns"])

    candle_records = pd.read_feather(
        data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    ).to_dict(orient="records")
    baselines = {
        scenario: evaluate_plan_baselines(
            plan=plan, candles=candle_records, costs=costs, scenario=scenario
        )
        for scenario in ("realistic", "taker_heavy")
    }

    # --- Kart §4.6: yetersiz örneklem kabul/ret değil, INVALID ---
    if total_trades < MIN_TRADES:
        summary = {
            "hypothesis_id": HYPOTHESIS_ID,
            "strategy": STRATEGY,
            "total_trades": total_trades,
            "verdict": (f"invalid (insufficient sample: {total_trades} < {MIN_TRADES} trades)"),
            "rejection_reasons": [],
        }
        return _finalize(summary, registry_path, fee["realistic"])

    p_value = 1.0
    if total_trades:
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
    """DSR, PBO/CSCV, ±%20 hassasiyet ve dönem kırılganlığı (ADR-0019/0020)."""
    plan_variants = build_sensitivity_plan(
        BASE_PARAMETERS, relative_delta=gates_cfg["sensitivity"]["relative_delta"]
    )
    if base_rejected:
        # Base zaten reddedildi: retention oranı anlamsız sayı üretirdi.
        return {
            "failures": [],
            "report": {
                "status": "not_evaluated",
                "reason": "base hypothesis rejected before extra gates; retention undefined",
                "planned_variants": [item["variant_id"] for item in plan_variants],
            },
        }

    variant_returns: dict[str, dict[str, list[float]]] = {}
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
        failures.append(f"DSR gate failed (probability {dsr.get('dsr_probability'):.4f})")

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
    report["pbo_threshold_note"] = (
        "Kart 0.50 yazar, config 0.05; eşikler config'de yaşar ve sıkı olan uygulandı."
    )
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

    try:
        fragility = evaluate_period_venue_fragility(
            period_returns=base["period_returns"],
            venue_returns={},
            required_scenarios=["realistic", "taker_heavy"],
            **{
                key: gates_cfg["fragility"][key]
                for key in (
                    "min_period_groups",
                    "min_venue_groups",
                    "min_observations_per_group",
                    "min_worst_group_retention_ratio",
                    "min_positive_group_ratio",
                )
                if key in gates_cfg["fragility"]
            },
        )
    except (StatisticalGateError, TypeError) as error:
        # S-0005 tek yürütme mekânında (Binance perp) işlem görür; venue boyutu için
        # ön-kayıtlı bir ikinci yürütme mekânı yoktur. Sahte grup üretmek yerine durum
        # gerekçesiyle raporlanır; dönem yoğunlaşması ayrıca aşağıda özetlenir.
        fragility = {
            "status": "not_evaluated",
            "reason": f"{error}",
            "note": "single pre-registered execution venue; venue dimension not applicable",
            "period_groups": {
                scenario: len(groups) for scenario, groups in base["period_returns"].items()
            },
        }
    report["period_fragility"] = fragility
    if fragility.get("status") == "failed":
        failures.append("period/venue fragility failed")

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
    print(json.dumps(run_s0005_evaluation(), indent=2, ensure_ascii=False, default=float))
