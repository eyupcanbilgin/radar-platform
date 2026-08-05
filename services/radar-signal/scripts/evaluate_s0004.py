"""S-0004 (Volatilite Rejimi Koşullandırmalı Trend) Değerlendirme ve Ölçüm Motoru.

Bu script S-0004 hipotez kartındaki kuralları birebir ve sızıntısız uygular:
1. Purged Walk-Forward split planı (walk_forward_lib.py) ile YALNIZ Development penceresi.
2. 30 günlük rolling fiyat persentili ile YÖN (P_price > 0.50 UP, < 0.50 DOWN).
3. 14 günlük gerçekleşen volatilitenin 60 günlük persentili (P_vol) ile KAPILAMA
   (0.20 <= P_vol <= 0.80).
4. Volatilite engelli rejimlerde WAIT (0 pozisyon); bu dönemler sıfır getiri üretir.
5. Maliyet sonrası değerlendirme: config/costs.yaml (realistic ve taker_heavy).
6. Baseline kıyası: baseline_evaluator.py (cash, buy_and_hold, simple_trend).
7. İstatistiksel anlamlılık (pulse_stats.py) permütasyon testi p-değeri.
8. Sonucun Experiment Registry (registrylib.py / experiments.jsonl) kütüğüne yazımı.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.baseline_evaluator import evaluate_plan_baselines
from scripts.costslib import effective_fee, load_costs
from scripts.datapaths import data_dir, verify_manifest
from scripts.provenance import environment_fingerprint
from scripts.pulse_stats import moving_block_test, non_overlapping_positions
from scripts.registrylib import (
    git_commit_hash,
    latest_manifest_hash,
    read_all,
    record_run,
)
from scripts.walk_forward_lib import (
    generate_walk_forward_plan,
    load_research_protocol_config,
    parse_utc_datetime,
)


def load_candle_data() -> pd.DataFrame:
    """1h futures mum verilerini yükler."""
    cpath = data_dir() / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    if not cpath.exists():
        raise FileNotFoundError(f"Gerekli mum veri dosyası bulunamadı: {cpath}")

    c_df = pd.read_feather(cpath)
    c_df["date_dt"] = pd.to_datetime(c_df["date"], utc=True)
    c_df = c_df.sort_values("date_dt").reset_index(drop=True)
    return c_df


def compute_s0004_signals(
    c_df: pd.DataFrame,
    trend_days: int = 30,
    vol_calc_days: int = 14,
    vol_dist_days: int = 60,
    vol_lower_pct: float = 0.20,
    vol_upper_pct: float = 0.80,
) -> pd.DataFrame:
    """S-0004 trend ve volatilite kapısı sinyallerini hesaplar."""
    df = c_df.copy()

    trend_bars = trend_days * 24
    vol_calc_bars = vol_calc_days * 24
    vol_dist_bars = vol_dist_days * 24

    # 1. Trend indicator: 30-day (720h) rolling price percentile rank
    def _pct_rank(arr: np.ndarray) -> float:
        if len(arr) < trend_bars // 2:
            return np.nan
        val = arr[-1]
        if np.isnan(val):
            return np.nan
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return np.nan
        return float((valid <= val).mean())

    df["price_pct"] = (
        df["close"]
        .rolling(window=trend_bars, min_periods=trend_bars // 2)
        .apply(_pct_rank, raw=True)
    )

    # 2. Volatility metric: 14-day (336h) realized volatility (std of log returns)
    log_returns = np.log(df["close"] / df["close"].shift(1))
    df["realized_vol"] = log_returns.rolling(
        window=vol_calc_bars, min_periods=vol_calc_bars // 2
    ).std()

    # 3. Volatility gate: 60-day (1440h) rolling percentile of realized vol
    def _vol_pct_rank(arr: np.ndarray) -> float:
        if len(arr) < vol_dist_bars // 2:
            return np.nan
        val = arr[-1]
        if np.isnan(val):
            return np.nan
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return np.nan
        return float((valid <= val).mean())

    df["vol_pct"] = (
        df["realized_vol"]
        .rolling(window=vol_dist_bars, min_periods=vol_dist_bars // 2)
        .apply(_vol_pct_rank, raw=True)
    )

    # Signal logic:
    # Allowed vol band: vol_lower_pct <= vol_pct <= vol_upper_pct
    # Price pct > 0.50 -> LONG (+1), Price pct < 0.50 -> SHORT (-1)
    # Vol outside band -> WAIT (0)
    cond_valid_vol = (df["vol_pct"] >= vol_lower_pct) & (df["vol_pct"] <= vol_upper_pct)
    cond_long = cond_valid_vol & (df["price_pct"] > 0.50)
    cond_short = cond_valid_vol & (df["price_pct"] < 0.50)

    conditions = [cond_long, cond_short]
    choices = [1, -1]  # 1: LONG, -1: SHORT
    df["signal"] = np.select(conditions, choices, default=0)

    # 24h forward returns on all candles for null distribution calculation
    closes = df["close"].values
    opens = df["open"].values
    n_candles = len(df)

    fwd_24h = np.full(n_candles, np.nan, dtype=float)
    for i in range(n_candles - 24):
        p_in = opens[i + 1]
        p_out = closes[i + 24]
        if p_in > 0:
            fwd_24h[i] = (p_out - p_in) / p_in

    df["fwd_24h_raw"] = fwd_24h

    return df


def run_s0004_evaluation(registry_path: Path | None = None) -> dict:
    manifest_info = verify_manifest()
    if manifest_info.get("status") != "ok":
        raise ValueError(f"Veri manifest doğrulaması başarısız: {manifest_info}")

    protocol_cfg = load_research_protocol_config()
    costs_cfg = load_costs()

    c_df = load_candle_data()
    df_signals = compute_s0004_signals(c_df)

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
        "hypothesis_id": "S-0004",
        "strategy": "S0004VolConditionedTrend",
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

    existing_runs = [
        r
        for r in read_all(registry_path)
        if r.get("hypothesis_id") == "S-0004"
        and r.get("strategy_version") == git_commit_hash()
        and r.get("dataset_snapshot") == latest_manifest_hash()
        and not r.get("verdict", "").startswith("invalid")
    ]
    if existing_runs:
        reg_entry = existing_runs[0]
    else:
        reg_entry = record_run(
            registry_path=registry_path,
            hypothesis_id="S-0004",
            strategy="S0004VolConditionedTrend",
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
    res = run_s0004_evaluation()
    print(json.dumps(res, indent=2, ensure_ascii=False))
