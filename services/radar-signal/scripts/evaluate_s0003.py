"""S-0003 (Aşırı Settled Funding Yönsel Reversal) Değerlendirme ve Ölçüm Motoru.

Bu script S-0003 hipotez kartındaki kuralları birebir ve sızıntısız uygular:
1. Purged Walk-Forward split planı (walk_forward_lib.py) ile YALNIZ Development penceresi.
2. Settled funding yayın-anı kuralı: available_at <= karar_anı (look-ahead yok).
3. 30 günlük rolling persentil: >=95% SHORT, <=5% LONG.
4. Maliyet sonrası değerlendirme: config/costs.yaml (realistic ve taker_heavy).
5. Baseline kıyası: baseline_evaluator.py (cash, buy_and_hold, simple_trend).
6. İstatistiksel anlamlılık (pulse_stats.py) permütasyon testi p-değeri.
7. Sonucun Experiment Registry (registrylib.py / experiments.jsonl) kütüğüne yazımı.
"""

import json

import numpy as np
import pandas as pd

from scripts.baseline_evaluator import evaluate_plan_baselines
from scripts.costslib import effective_fee, load_costs
from scripts.datapaths import data_dir, verify_manifest
from scripts.provenance import environment_fingerprint
from scripts.pulse_stats import moving_block_test, non_overlapping_positions
from scripts.registrylib import record_run
from scripts.walk_forward_lib import (
    generate_walk_forward_plan,
    load_research_protocol_config,
    parse_utc_datetime,
)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Funding ve 1h futures mum verilerini yükler."""
    fpath = data_dir() / "futures" / "BTC_USDT_USDT-1h-funding_rate.feather"
    cpath = data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"

    if not fpath.exists() or not cpath.exists():
        raise FileNotFoundError("Gerekli veri dosyaları bulunamadı!")

    fr_df = pd.read_feather(fpath)
    c_df = pd.read_feather(cpath)

    fr_df["date_dt"] = pd.to_datetime(fr_df["date"], utc=True)
    c_df["date_dt"] = pd.to_datetime(c_df["date"], utc=True)

    fr_df = fr_df.sort_values("date_dt").reset_index(drop=True)
    c_df = c_df.sort_values("date_dt").reset_index(drop=True)

    return fr_df, c_df


def compute_funding_signals(
    fr_df: pd.DataFrame, c_df: pd.DataFrame, rolling_days: int = 30
) -> pd.DataFrame:
    """Yayın-anı kuralına uygun 30 günlük rolling persentil ve S-0003 sinyallerini türetir."""
    merged = pd.merge_asof(
        c_df,
        fr_df[["date_dt", "open"]].rename(columns={"open": "funding_rate"}),
        on="date_dt",
        direction="backward",
    )

    window_bars = rolling_days * 24

    def _pct_rank(arr: np.ndarray) -> float:
        if len(arr) < window_bars // 2:
            return np.nan
        val = arr[-1]
        if np.isnan(val):
            return np.nan
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return np.nan
        return float((valid <= val).mean())

    merged["funding_pct"] = (
        merged["funding_rate"]
        .rolling(window=window_bars, min_periods=window_bars // 2)
        .apply(_pct_rank, raw=True)
    )

    conditions = [
        (merged["funding_pct"] >= 0.95),
        (merged["funding_pct"] <= 0.05),
    ]
    choices = [-1, 1]  # -1: SHORT, +1: LONG
    merged["signal"] = np.select(conditions, choices, default=0)

    # 24h forward returns on all candles for null distribution calculation
    closes = merged["close"].values
    opens = merged["open"].values
    n_candles = len(merged)

    fwd_24h = np.full(n_candles, np.nan, dtype=float)
    for i in range(n_candles - 24):
        p_in = opens[i + 1]
        p_out = closes[i + 24]
        if p_in > 0:
            fwd_24h[i] = (p_out - p_in) / p_in

    merged["fwd_24h_raw"] = fwd_24h

    return merged


def run_s0003_evaluation() -> dict:
    # STEP 2: Manifest kontrolü
    manifest_info = verify_manifest()
    if manifest_info.get("status") != "ok":
        raise ValueError(f"Veri manifest doğrulaması başarısız: {manifest_info}")

    protocol_cfg = load_research_protocol_config()
    costs_cfg = load_costs()

    fr_df, c_df = load_data()
    df_signals = compute_funding_signals(fr_df, c_df, rolling_days=30)

    # Purged Walk-Forward plan (Development dönemi)
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        horizon_hours=24,
        allow_locked_oos=False,
        config=protocol_cfg,
    )

    candles_dict_list = c_df.to_dict(orient="records")

    baselines_realistic = evaluate_plan_baselines(
        plan=plan, candles=candles_dict_list, costs=costs_cfg, scenario="realistic"
    )
    baselines_taker = evaluate_plan_baselines(
        plan=plan, candles=candles_dict_list, costs=costs_cfg, scenario="taker_heavy"
    )

    fee_real = effective_fee(costs_cfg, "realistic")
    fee_taker = effective_fee(costs_cfg, "taker_heavy")

    fold_results = []
    all_trade_raw_returns = []
    all_trade_net_real = []
    all_trade_net_taker = []
    all_trade_signals = []

    positive_folds_real = 0
    positive_folds_taker = 0
    total_valid_folds = 0

    for fold in plan["folds"]:
        te_start_dt = parse_utc_datetime(fold["test_start_utc"])
        te_end_dt = parse_utc_datetime(fold["test_end_utc"])

        sub_df = df_signals[
            (df_signals["date_dt"] >= te_start_dt) & (df_signals["date_dt"] < te_end_dt)
        ].copy()

        sig_mask = sub_df["signal"].values != 0
        non_overlap_indices = non_overlapping_positions(sig_mask, horizon=24)

        fold_raw_rets = []
        fold_net_real_rets = []
        fold_net_taker_rets = []

        for idx_rel in non_overlap_indices:
            idx = sub_df.index[idx_rel]
            loc = df_signals.index.get_loc(idx)
            if loc + 24 >= len(df_signals):
                continue

            entry_price = float(df_signals.iloc[loc + 1]["open"])
            exit_price = float(df_signals.iloc[loc + 24]["close"])

            if entry_price <= 0 or exit_price <= 0:
                continue

            sig = int(df_signals.iloc[loc]["signal"])
            if sig == 1:  # LONG
                r_raw = (exit_price - entry_price) / entry_price
            else:  # SHORT (-1)
                r_raw = (entry_price - exit_price) / entry_price

            r_net_real = (1.0 + r_raw) * (1.0 - fee_real) / (1.0 + fee_real) - 1.0
            r_net_taker = (1.0 + r_raw) * (1.0 - fee_taker) / (1.0 + fee_taker) - 1.0

            fold_raw_rets.append(r_raw)
            fold_net_real_rets.append(r_net_real)
            fold_net_taker_rets.append(r_net_taker)
            all_trade_signals.append(sig)

        trade_cnt = len(fold_raw_rets)
        if trade_cnt > 0:
            avg_net_real = float(np.mean(fold_net_real_rets))
            avg_net_taker = float(np.mean(fold_net_taker_rets))
            cum_net_real = float(np.prod([1.0 + r for r in fold_net_real_rets]) - 1.0)
            cum_net_taker = float(np.prod([1.0 + r for r in fold_net_taker_rets]) - 1.0)
        else:
            avg_net_real = 0.0
            avg_net_taker = 0.0
            cum_net_real = 0.0
            cum_net_taker = 0.0

        if fold.get("status") == "valid":
            total_valid_folds += 1
            if cum_net_real > 0:
                positive_folds_real += 1
            if cum_net_taker > 0:
                positive_folds_taker += 1

        all_trade_raw_returns.extend(fold_raw_rets)
        all_trade_net_real.extend(fold_net_real_rets)
        all_trade_net_taker.extend(fold_net_taker_rets)

        fold_results.append(
            {
                "fold_index": fold["fold_index"],
                "test_start_utc": fold["test_start_utc"],
                "test_end_utc": fold["test_end_utc"],
                "trade_count": trade_cnt,
                "realistic": {
                    "avg_net_return": avg_net_real,
                    "cum_net_return": cum_net_real,
                },
                "taker_heavy": {
                    "avg_net_return": avg_net_taker,
                    "cum_net_return": cum_net_taker,
                },
            }
        )

    total_trades = len(all_trade_raw_returns)
    if total_trades > 0:
        agg_cum_real = float(np.prod([1.0 + r for r in all_trade_net_real]) - 1.0)
        agg_cum_taker = float(np.prod([1.0 + r for r in all_trade_net_taker]) - 1.0)
        agg_avg_real = float(np.mean(all_trade_net_real))
        agg_avg_taker = float(np.mean(all_trade_net_taker))

        # Perform time-series safe moving block test against null base
        base_rets = df_signals["fwd_24h_raw"].dropna().values * 10000.0  # bps
        signal_bps = np.array(all_trade_raw_returns) * 10000.0
        long_share = float(np.mean([1 if s == 1 else 0 for s in all_trade_signals]))

        rng = np.random.default_rng(42)
        p_val_dict = moving_block_test(
            signal_values=signal_bps,
            base=base_rets,
            long_share=long_share,
            n_bootstrap=2000,
            rng=rng,
            mode="directional",
            block_size=24,
        )
        p_value = float(p_val_dict.get("p_greater", 1.0))
    else:
        agg_cum_real = 0.0
        agg_cum_taker = 0.0
        agg_avg_real = 0.0
        agg_avg_taker = 0.0
        p_value = 1.0

    fold_positive_ratio = (
        float(positive_folds_real / total_valid_folds) if total_valid_folds > 0 else 0.0
    )

    b_real_bnh = float(
        np.prod(
            [
                1.0 + (f["baselines"]["buy_and_hold"]["net_return"] or 0.0)
                for f in baselines_realistic["evaluated_folds"]
            ]
        )
        - 1.0
    )
    b_real_trend = float(
        np.prod(
            [
                1.0 + (f["baselines"]["simple_trend"]["net_return"] or 0.0)
                for f in baselines_realistic["evaluated_folds"]
            ]
        )
        - 1.0
    )

    b_taker_bnh = float(
        np.prod(
            [
                1.0 + (f["baselines"]["buy_and_hold"]["net_return"] or 0.0)
                for f in baselines_taker["evaluated_folds"]
            ]
        )
        - 1.0
    )
    b_taker_trend = float(
        np.prod(
            [
                1.0 + (f["baselines"]["simple_trend"]["net_return"] or 0.0)
                for f in baselines_taker["evaluated_folds"]
            ]
        )
        - 1.0
    )

    rejection_reasons = []
    if agg_cum_real <= 0:
        rejection_reasons.append("realistic net_return <= 0")
    if agg_cum_taker <= 0:
        rejection_reasons.append("taker_heavy net_return <= 0")
    if agg_cum_real <= b_real_bnh:
        rejection_reasons.append("failed to beat realistic buy_and_hold baseline")
    if agg_cum_real <= b_real_trend:
        rejection_reasons.append("failed to beat realistic simple_trend baseline")
    if agg_cum_taker <= b_taker_bnh:
        rejection_reasons.append("failed to beat taker_heavy buy_and_hold baseline")
    if agg_cum_taker <= b_taker_trend:
        rejection_reasons.append("failed to beat taker_heavy simple_trend baseline")
    if p_value >= 0.05:
        rejection_reasons.append(f"bootstrap p-value {p_value:.4f} >= 0.05")
    if fold_positive_ratio < 0.60:
        rejection_reasons.append(f"fold consistency {fold_positive_ratio:.1%} < 60%")

    is_rejected = len(rejection_reasons) > 0
    verdict = (
        f"rejected ({'; '.join(rejection_reasons)})"
        if is_rejected
        else "accepted (Development level)"
    )

    summary = {
        "hypothesis_id": "S-0003",
        "strategy": "S0003FundingExtreme",
        "timerange": "2024-01-01T00:00:00Z -> 2026-08-04T00:00:00Z",
        "total_trades": total_trades,
        "valid_folds_count": total_valid_folds,
        "fold_positive_ratio": fold_positive_ratio,
        "bootstrap_p_value": p_value,
        "performance": {
            "realistic": {
                "cum_net_return": agg_cum_real,
                "avg_net_return": agg_avg_real,
                "baseline_bnh_return": b_real_bnh,
                "baseline_trend_return": b_real_trend,
            },
            "taker_heavy": {
                "cum_net_return": agg_cum_taker,
                "avg_net_return": agg_avg_taker,
                "baseline_bnh_return": b_taker_bnh,
                "baseline_trend_return": b_taker_trend,
            },
        },
        "verdict": verdict,
        "rejection_reasons": rejection_reasons,
    }

    reg_entry = record_run(
        hypothesis_id="S-0003",
        strategy="S0003FundingExtreme",
        scenario="realistic_and_taker_heavy",
        effective_fee=fee_real,
        exit_code=0,
        verdict=verdict,
        result=summary,
        pairs=["BTC/USDT:USDT"],
        created_by="claude",
    )

    summary["registry_experiment_id"] = reg_entry["experiment_id"]
    summary["provenance"] = environment_fingerprint()

    return summary


if __name__ == "__main__":
    res = run_s0003_evaluation()
    print(json.dumps(res, indent=2, ensure_ascii=False))
