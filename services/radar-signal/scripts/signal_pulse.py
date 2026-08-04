"""Hipotez Eleme Tezgâhı — Hipotez Kartları (A, B, C, D, E, I, J, K, L, M) Nabız Teşhis Motoru.

Bu script, strateji kodu yazılmadan önce tüm test edilebilir hipotez kartlarının ham öngörü
gücünü (yönsel getiri beklentisi ve volatilite genişleme oranı) ölçer.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))
from datapaths import data_dir  # noqa: E402
from provenance import environment_fingerprint  # noqa: E402
from pulse_stats import (  # noqa: E402
    benjamini_hochberg,
    moving_block_test,
    non_overlapping_positions,
)

HORIZONS = (1, 2, 4, 8, 16)
ROUNDTRIP_COST_BPS_BTC = 17.0
ROUNDTRIP_COST_BPS_ETH = 20.0


def load_fomc_calendar() -> pd.DataFrame:
    path = SERVICE_ROOT / "config" / "fomc_calendar.csv"
    if not path.exists():
        raise FileNotFoundError(f"FOMC takvimi bulunamadı: {path}")
    df = pd.read_csv(path, comment="#")
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["utc_time"], utc=True)
    return df


def load_pair_15m(symbol: str, start: str, end: str) -> pd.DataFrame:
    path = data_dir() / "futures" / f"{symbol}_USDT_USDT-15m-futures.feather"
    if not path.exists():
        raise FileNotFoundError(f"veri yok: {path}")
    df = pd.read_feather(path)
    df = df[(df["date"] >= start) & (df["date"] < end)].reset_index(drop=True)

    fpath = data_dir() / "futures" / f"{symbol}_USDT_USDT-1h-funding_rate.feather"
    if fpath.exists():
        fr = pd.read_feather(fpath)[["date", "open"]].rename(columns={"open": "funding_rate"})
        df = pd.merge_asof(
            df.sort_values("date"), fr.sort_values("date"), on="date", direction="backward"
        )
    else:
        df["funding_rate"] = np.nan
    return df


def load_pair_1m(symbol: str, start: str, end: str) -> pd.DataFrame:
    path = data_dir() / "futures" / f"{symbol}_USDT_USDT-1m-futures.feather"
    if not path.exists():
        raise FileNotFoundError(f"1m veri yok: {path}")
    df = pd.read_feather(path)
    df = df[(df["date"] >= start) & (df["date"] < end)].reset_index(drop=True)
    return df


def _add_forward_returns(df: pd.DataFrame, horizons: tuple[int, ...]) -> None:
    """Add next-open-to-future-close returns available after a closed decision candle."""
    next_open = df["open"].shift(-1)
    for horizon in horizons:
        df[f"fwd_{horizon}"] = df["close"].shift(-horizon) / next_open - 1.0


def _forward_volatility_ratio(
    returns: pd.Series,
    horizon: int,
    baseline_window: int,
) -> pd.Series:
    """Forward realized volatility divided by trailing realized volatility.

    RMS volatility is defined for a one-bar horizon, unlike sample std with ``ddof=1``.
    """
    forward_variance = (
        returns.pow(2)
        .shift(-horizon)
        .rolling(
            horizon,
            min_periods=horizon,
        )
        .mean()
    )
    baseline_variance = (
        returns.pow(2)
        .rolling(
            baseline_window,
            min_periods=max(4, baseline_window // 4),
        )
        .mean()
    )
    return np.sqrt(forward_variance) / np.maximum(1e-12, np.sqrt(baseline_variance))


def _episode_start(mask: pd.Series) -> pd.Series:
    """Mark only the first bar of each contiguous event episode."""
    filled = mask.fillna(False).astype(bool)
    return filled & ~filled.shift(1, fill_value=False)


def permutation_test(
    signal_vals: np.ndarray,
    base: np.ndarray,
    long_share: float,
    n_perm: int,
    rng: np.random.Generator,
    mode: str = "directional",
    block_size: int = 4,
) -> dict:
    """Backward-compatible wrapper around the time-series-safe bootstrap test."""
    bootstrap_mode = "directional" if mode == "directional" else "level"
    return moving_block_test(
        signal_vals,
        base,
        long_share,
        n_perm,
        rng,
        mode=bootstrap_mode,
        block_size=block_size,
    )


# =====================================================================
# SİNYAL OLUŞTURUCULARI (Kartlar A, B, C, D, E, I, J, K, L, M)
# =====================================================================


def build_signals_card_a(df: pd.DataFrame, window: int) -> pd.DataFrame:
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["return_4bar"] = d["close"].pct_change(4)
    d["rank"] = d.groupby("hour")["return_4bar"].transform(
        lambda x: x.rolling(window, min_periods=max(10, window // 8)).rank(pct=True)
    )
    d["volume_1h"] = d["volume"].rolling(4).sum()
    d["vol_median"] = d.groupby("hour")["volume_1h"].transform(
        lambda x: x.rolling(window, min_periods=max(10, window // 8)).median()
    )
    d["hmax"] = d["high"].shift(1).rolling(4).max()
    d["lmin"] = d["low"].shift(1).rolling(4).min()

    if d["funding_rate"].notna().any():
        fr_rank = d["funding_rate"].rolling(1920, min_periods=96).rank(pct=True)
        d["funding_ok"] = (fr_rank >= 0.05) & (fr_rank <= 0.95)
    else:
        d["funding_ok"] = True

    vol_ok = d["volume_1h"] >= 1.25 * d["vol_median"]
    long_sig = (d["rank"] >= 0.80) & vol_ok & (d["close"] > d["hmax"]) & d["funding_ok"]
    short_sig = (d["rank"] <= 0.20) & vol_ok & (d["close"] < d["lmin"]) & d["funding_ok"]
    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))

    _add_forward_returns(d, HORIZONS)
    return d


def build_signals_card_b(df: pd.DataFrame) -> pd.DataFrame:
    """Kart B — Jump-reversal (likidasyonsuz kısım). Şok yönünün TERSİNE sinyal."""
    d = df.copy()
    ret_15m = d["close"].pct_change(1)
    ret_mean = ret_15m.rolling(1920, min_periods=240).mean()
    ret_std = ret_15m.rolling(1920, min_periods=240).std()
    ret_z = (ret_15m - ret_mean) / ret_std

    vol_mean = d["volume"].rolling(1920, min_periods=240).mean()
    vol_std = d["volume"].rolling(1920, min_periods=240).std()
    vol_z = (d["volume"] - vol_mean) / vol_std

    long_contrarian = (ret_z < -3.0) & (vol_z > 3.0)  # Aşırı düşüş sonrası LONG
    short_contrarian = (ret_z > 3.0) & (vol_z > 3.0)  # Aşırı yükseliş sonrası SHORT

    d["direction"] = np.where(long_contrarian, 1, np.where(short_contrarian, -1, 0))

    _add_forward_returns(d, HORIZONS)
    return d


def build_signals_card_c(df: pd.DataFrame) -> pd.DataFrame:
    """Kart C — AB/ABD Seansı (12:00-20:00 UTC) ilk 30m -> son momentum."""
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["minute"] = d["date"].dt.minute

    is_session_open_eval = (d["hour"] == 12) & (d["minute"] == 30)
    ret_first_30m = d["close"] / d["close"].shift(2) - 1.0
    vol_first_30m = d["volume"].rolling(2).sum()
    session_open_volume = vol_first_30m[is_session_open_eval]
    session_threshold = session_open_volume.shift(1).rolling(90, min_periods=20).quantile(0.70)
    vol_30m_p70 = pd.Series(np.nan, index=d.index, dtype=float)
    vol_30m_p70.loc[session_threshold.index] = session_threshold

    sig_long = is_session_open_eval & (ret_first_30m > 0) & (vol_first_30m > vol_30m_p70)
    sig_short = is_session_open_eval & (ret_first_30m < 0) & (vol_first_30m > vol_30m_p70)

    d["direction"] = np.where(sig_long, 1, np.where(sig_short, -1, 0))

    _add_forward_returns(d, (2, 4, 16))
    return d


def build_signals_card_d(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Kart D — 15m mum sınırı anomalisi (1m veri ile)."""
    d = df_1m.copy()
    d["minute"] = d["date"].dt.minute
    d["is_boundary"] = d["minute"].isin([59, 0, 14, 15, 29, 30, 44, 45])
    d["fwd_1m"] = d["close"].shift(-1) / d["open"].shift(-1) - 1.0
    d["direction"] = np.where(d["is_boundary"], 1, 0)
    return d


def build_signals_card_e(df: pd.DataFrame) -> pd.DataFrame:
    """Kart E — Aşırı funding -> volatilite genişlemesi & yön."""
    d = df.copy()
    fr = d["funding_rate"]
    fr_mean = fr.rolling(1920, min_periods=240).mean()
    fr_std = fr.rolling(1920, min_periods=240).std()
    fr_z = (fr - fr_mean) / fr_std

    high_funding = fr_z > 2.0
    event_start = _episode_start(high_funding)
    d["direction"] = np.where(event_start, 1, 0)
    d["event_trigger"] = event_start.astype(int)

    ret_short = d["close"].pct_change()
    for h in (4, 8, 16):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_short, h, 96)
    _add_forward_returns(d, (4, 8, 16))
    return d


def build_signals_card_i(df: pd.DataFrame, session: str) -> pd.DataFrame:
    """Kart I — DST-aware London/NY local market opening activity."""
    d = df.copy()
    if session == "london":
        local_time = d["date"].dt.tz_convert("Europe/London")
        is_eval_bar = (local_time.dt.hour == 8) & (local_time.dt.minute == 0)
    elif session == "ny":
        local_time = d["date"].dt.tz_convert("America/New_York")
        is_eval_bar = (local_time.dt.hour == 9) & (local_time.dt.minute == 30)
    else:
        raise ValueError(f"bilinmeyen seans: {session}")

    pre_high = d["high"].shift(1).rolling(4).max()
    pre_low = d["low"].shift(1).rolling(4).min()

    long_orb = is_eval_bar & (d["close"] > pre_high)
    short_orb = is_eval_bar & (d["close"] < pre_low)
    d["direction"] = np.where(long_orb, 1, np.where(short_orb, -1, 0))
    d["event_trigger"] = np.where(is_eval_bar, 1, 0)

    ret_15m = d["close"].pct_change()
    for h in (1, 2, 4):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_15m, h, 4)
    _add_forward_returns(d, (1, 2, 4))
    return d


def build_signals_card_j(df: pd.DataFrame) -> pd.DataFrame:
    """Kart J — Hafta sonu geçişi volatilite ve breakout."""
    d = df.copy()
    d["dayofweek"] = d["date"].dt.dayofweek
    d["is_weekend"] = d["dayofweek"].isin([5, 6])
    weekend_start = _episode_start(d["is_weekend"])

    hmax_4h = d["high"].shift(1).rolling(16).max()
    lmin_4h = d["low"].shift(1).rolling(16).min()
    long_sig = weekend_start & (d["close"] > hmax_4h)
    short_sig = weekend_start & (d["close"] < lmin_4h)

    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    d["event_trigger"] = weekend_start.astype(int)

    ret_15m = d["close"].pct_change()
    for h in (1, 2, 4, 8):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_15m, h, 96)
    _add_forward_returns(d, (1, 2, 4, 8))
    return d


def build_signals_card_k(df: pd.DataFrame, fomc_df: pd.DataFrame) -> pd.DataFrame:
    """Kart K — FOMC duyurusu volatilite sıçraması ve ORB."""
    d = df.copy()
    d["is_fomc_bar"] = False

    for fomc_dt in fomc_df["datetime"]:
        diffs = (d["date"] - fomc_dt).abs()
        min_idx = diffs.idxmin()
        if diffs.loc[min_idx] <= pd.Timedelta(minutes=15):
            d.loc[min_idx, "is_fomc_bar"] = True

    eval_bar = d["is_fomc_bar"].shift(1).fillna(False)
    fomc_high = d["high"].shift(1)
    fomc_low = d["low"].shift(1)

    long_sig = eval_bar & (d["close"] > fomc_high)
    short_sig = eval_bar & (d["close"] < fomc_low)
    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    d["event_trigger"] = np.where(d["is_fomc_bar"], 1, 0)

    ret_15m = d["close"].pct_change()
    for h in (1, 2, 4):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_15m, h, 96)
    _add_forward_returns(d, (1, 2, 4))
    return d


def build_signals_card_l(df: pd.DataFrame) -> pd.DataFrame:
    """Kart L — Volatilite kümelenmesi (`RV_short / RV_long`) rejim devamı."""
    d = df.copy()
    ret_15m = d["close"].pct_change()
    rv_short = ret_15m.rolling(4).std()
    rv_long = ret_15m.rolling(96).std()
    regime_ratio = rv_short / np.maximum(1e-6, rv_long)

    high_vol_regime = regime_ratio > regime_ratio.rolling(1920, min_periods=240).quantile(0.80)
    event_start = _episode_start(high_vol_regime)

    hmax_4h = d["high"].shift(1).rolling(16).max()
    lmin_4h = d["low"].shift(1).rolling(16).min()
    long_sig = event_start & (d["close"] > hmax_4h)
    short_sig = event_start & (d["close"] < lmin_4h)

    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    d["event_trigger"] = event_start.astype(int)

    for h in (4, 8, 16):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_15m, h, 96)
    _add_forward_returns(d, (4, 8, 16))
    return d


def build_signals_card_m(df: pd.DataFrame) -> pd.DataFrame:
    """Kart M — Deribit settlement 08:00 UTC aktivitesi."""
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["minute"] = d["date"].dt.minute

    is_0800_bar = (d["hour"] == 8) & (d["minute"] == 0)
    d["direction"] = np.where(is_0800_bar, 1, 0)
    d["event_trigger"] = np.where(is_0800_bar, 1, 0)

    ret_15m = d["close"].pct_change()
    for h in (1, 2, 4):
        d[f"vol_ratio_{h}"] = _forward_volatility_ratio(ret_15m, h, 96)
    _add_forward_returns(d, (1, 2, 4))
    return d


# =====================================================================
# ELEME BENCHMARK ÇALIŞTIRICI
# =====================================================================


def _selected_rows(
    frame: pd.DataFrame,
    mask: pd.Series,
    value_column: str,
    horizon: int,
) -> tuple[pd.DataFrame, int]:
    eligible = mask.fillna(False).to_numpy(dtype=bool) & frame[value_column].notna().to_numpy()
    raw_count = int(eligible.sum())
    positions = non_overlapping_positions(eligible, horizon)
    return frame.iloc[positions], raw_count


def _selected_p_value(test: dict[str, float], alternative: str) -> float:
    key = {
        "greater": "p_greater",
        "less": "p_less",
        "two-sided": "p_two_sided",
    }.get(alternative)
    if key is None:
        raise ValueError(f"geçersiz alternatif: {alternative}")
    return float(test[key])


def _append_directional_tests(
    records: list[dict],
    frame: pd.DataFrame,
    *,
    card: str,
    variant: str,
    symbol: str,
    horizons: tuple[int, ...],
    cost_threshold_bps: float,
    n_perm: int,
    rng: np.random.Generator,
    alternative: str = "greater",
    null_mode: str = "directional",
) -> None:
    signal_mask = frame["direction"] != 0
    for horizon in horizons:
        column = f"fwd_{horizon}"
        selected, raw_count = _selected_rows(frame, signal_mask, column, horizon)
        if null_mode == "directional":
            signal_values = (selected[column] * selected["direction"]).to_numpy(dtype=float)
            long_share = float((selected["direction"] == 1).mean()) if not selected.empty else 0.5
        else:
            signal_values = selected[column].to_numpy(dtype=float)
            long_share = 0.5
        baseline = frame[column].dropna().to_numpy(dtype=float)
        block_size = max(4, horizon)
        test = moving_block_test(
            signal_values,
            baseline,
            long_share,
            n_perm,
            rng,
            mode=null_mode,
            block_size=block_size,
        )
        p_raw = _selected_p_value(test, alternative)
        valid = bool(len(signal_values) >= 2 and np.isfinite(p_raw))
        mean_bps = float(signal_values.mean() * 1e4) if len(signal_values) else float("nan")
        records.append(
            {
                "card": card,
                "variant": variant,
                "symbol": symbol,
                "horizon": f"+{horizon}bar",
                "mode": "directional",
                "alternative": alternative,
                "raw_n_signals": raw_count,
                "n_signals": len(signal_values),
                "mean_bps": mean_bps,
                "hit_rate": (
                    float((signal_values > 0).mean()) if len(signal_values) else float("nan")
                ),
                "p_raw": p_raw if valid else float("nan"),
                "cost_threshold_bps": cost_threshold_bps,
                "economic_magnitude": bool(
                    np.isfinite(mean_bps) and abs(mean_bps) > cost_threshold_bps
                ),
                "beats_cost": bool(
                    alternative == "greater"
                    and np.isfinite(mean_bps)
                    and mean_bps > cost_threshold_bps
                ),
                "block_size": block_size,
                "valid": valid,
            }
        )


def _append_volatility_tests(
    records: list[dict],
    frame: pd.DataFrame,
    *,
    card: str,
    variant: str,
    symbol: str,
    horizons: tuple[int, ...],
    n_perm: int,
    rng: np.random.Generator,
    alternative: str,
) -> None:
    event_mask = frame["event_trigger"] == 1
    for horizon in horizons:
        column = f"vol_ratio_{horizon}"
        selected, raw_count = _selected_rows(frame, event_mask, column, horizon)
        signal_values = selected[column].to_numpy(dtype=float)
        baseline = frame[column].dropna().to_numpy(dtype=float)
        block_size = max(4, horizon)
        test = moving_block_test(
            signal_values,
            baseline,
            0.5,
            n_perm,
            rng,
            mode="level",
            block_size=block_size,
        )
        p_raw = _selected_p_value(test, alternative)
        valid = bool(len(signal_values) >= 2 and np.isfinite(p_raw))
        ratio_mean = float(signal_values.mean()) if len(signal_values) else float("nan")
        if alternative == "greater":
            matches_effect = bool(np.isfinite(ratio_mean) and ratio_mean > 1.0)
        elif alternative == "less":
            matches_effect = bool(np.isfinite(ratio_mean) and ratio_mean < 1.0)
        else:
            matches_effect = bool(np.isfinite(ratio_mean) and ratio_mean != 1.0)
        records.append(
            {
                "card": card,
                "variant": variant,
                "symbol": symbol,
                "horizon": f"+{horizon}bar",
                "mode": "volatility_ratio",
                "alternative": alternative,
                "raw_n_signals": raw_count,
                "n_signals": len(signal_values),
                "mean_bps": (ratio_mean - 1.0) * 100 if np.isfinite(ratio_mean) else float("nan"),
                "hit_rate": (
                    float((signal_values > 1.0).mean()) if len(signal_values) else float("nan")
                ),
                "p_raw": p_raw if valid else float("nan"),
                "cost_threshold_bps": 0.0,
                "economic_magnitude": matches_effect,
                "beats_cost": matches_effect,
                "block_size": block_size,
                "valid": valid,
            }
        )


def run_workbench(
    start: str = "2024-01-01",
    end: str = "2026-08-03",
    n_perm: int = 2000,
    seed: int = 20260804,
) -> dict:
    rng = np.random.default_rng(seed)
    fomc_df = load_fomc_calendar()
    all_test_records: list[dict] = []

    for symbol in ("BTC", "ETH"):
        cost_th = ROUNDTRIP_COST_BPS_BTC if symbol == "BTC" else ROUNDTRIP_COST_BPS_ETH
        df_15m = load_pair_15m(symbol, start, end)
        df_1m = load_pair_1m(symbol, start, end)

        for wname, wval in [("20g", 80), ("60g", 240)]:
            da = build_signals_card_a(df_15m, wval)
            _append_directional_tests(
                all_test_records,
                da,
                card="A",
                variant=f"Kart A ({wname})",
                symbol=symbol,
                horizons=HORIZONS,
                cost_threshold_bps=cost_th,
                n_perm=n_perm,
                rng=rng,
            )

        db = build_signals_card_b(df_15m)
        _append_directional_tests(
            all_test_records,
            db,
            card="B",
            variant="Kart B (Jump-reversal)",
            symbol=symbol,
            horizons=HORIZONS,
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
        )

        dc = build_signals_card_c(df_15m)
        _append_directional_tests(
            all_test_records,
            dc,
            card="C",
            variant="Kart C (Seans momentum)",
            symbol=symbol,
            horizons=(2, 4, 16),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
        )

        dd = build_signals_card_d(df_1m)
        boundary_values = dd.loc[dd["is_boundary"], "fwd_1m"].dropna().to_numpy(dtype=float)
        non_boundary_values = dd.loc[~dd["is_boundary"], "fwd_1m"].dropna().to_numpy(dtype=float)
        test_d = moving_block_test(
            boundary_values,
            non_boundary_values,
            0.5,
            n_perm,
            rng,
            mode="level",
            block_size=15,
        )
        mean_boundary_bps = float(boundary_values.mean() * 1e4)
        p_d = float(test_d["p_two_sided"])
        all_test_records.append(
            {
                "card": "D",
                "variant": "Kart D (15m mum sınırı 1m)",
                "symbol": symbol,
                "horizon": "+1m",
                "mode": "directional",
                "alternative": "two-sided",
                "raw_n_signals": len(boundary_values),
                "n_signals": len(boundary_values),
                "mean_bps": mean_boundary_bps,
                "hit_rate": float((boundary_values > 0).mean()),
                "p_raw": p_d,
                "cost_threshold_bps": cost_th,
                "economic_magnitude": abs(mean_boundary_bps) > cost_th,
                "beats_cost": False,
                "block_size": 15,
                "valid": bool(np.isfinite(p_d)),
            }
        )

        de = build_signals_card_e(df_15m)
        _append_volatility_tests(
            all_test_records,
            de,
            card="E",
            variant="Kart E (Excess funding vol ratio)",
            symbol=symbol,
            horizons=(4, 8, 16),
            n_perm=n_perm,
            rng=rng,
            alternative="greater",
        )
        _append_directional_tests(
            all_test_records,
            de,
            card="E",
            variant="Kart E (Excess funding return; exploratory)",
            symbol=symbol,
            horizons=(4, 8, 16),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
            alternative="two-sided",
            null_mode="level",
        )

        for sname in ("london", "ny"):
            di = build_signals_card_i(df_15m, sname)
            _append_volatility_tests(
                all_test_records,
                di,
                card="I",
                variant=f"Kart I ({sname} vol ratio)",
                symbol=symbol,
                horizons=(1, 2, 4),
                n_perm=n_perm,
                rng=rng,
                alternative="greater",
            )
            _append_directional_tests(
                all_test_records,
                di,
                card="I",
                variant=f"Kart I ({sname} ORB return)",
                symbol=symbol,
                horizons=(1, 2, 4),
                cost_threshold_bps=cost_th,
                n_perm=n_perm,
                rng=rng,
            )

        dj = build_signals_card_j(df_15m)
        _append_volatility_tests(
            all_test_records,
            dj,
            card="J",
            variant="Kart J (Weekend transition vol ratio)",
            symbol=symbol,
            horizons=(1, 2, 4, 8),
            n_perm=n_perm,
            rng=rng,
            alternative="less",
        )
        _append_directional_tests(
            all_test_records,
            dj,
            card="J",
            variant="Kart J (Weekend transition breakout)",
            symbol=symbol,
            horizons=(1, 2, 4, 8),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
        )

        dk = build_signals_card_k(df_15m, fomc_df)
        _append_volatility_tests(
            all_test_records,
            dk,
            card="K",
            variant="Kart K (FOMC vol ratio)",
            symbol=symbol,
            horizons=(1, 2, 4),
            n_perm=n_perm,
            rng=rng,
            alternative="greater",
        )
        _append_directional_tests(
            all_test_records,
            dk,
            card="K",
            variant="Kart K (FOMC ORB return)",
            symbol=symbol,
            horizons=(1, 2, 4),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
        )

        dl = build_signals_card_l(df_15m)
        _append_volatility_tests(
            all_test_records,
            dl,
            card="L",
            variant="Kart L (Vol clustering ratio)",
            symbol=symbol,
            horizons=(4, 8, 16),
            n_perm=n_perm,
            rng=rng,
            alternative="greater",
        )
        _append_directional_tests(
            all_test_records,
            dl,
            card="L",
            variant="Kart L (Vol clustering momentum)",
            symbol=symbol,
            horizons=(4, 8, 16),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
        )

        dm = build_signals_card_m(df_15m)
        _append_volatility_tests(
            all_test_records,
            dm,
            card="M",
            variant="Kart M (08:00 UTC vol ratio)",
            symbol=symbol,
            horizons=(1, 2, 4),
            n_perm=n_perm,
            rng=rng,
            alternative="greater",
        )
        _append_directional_tests(
            all_test_records,
            dm,
            card="M",
            variant="Kart M (08:00 UTC return; exploratory)",
            symbol=symbol,
            horizons=(1, 2, 4),
            cost_threshold_bps=cost_th,
            n_perm=n_perm,
            rng=rng,
            alternative="two-sided",
            null_mode="level",
        )

    raw_p_list = [r["p_raw"] for r in all_test_records]
    adj_p_list = benjamini_hochberg(raw_p_list)

    for i, adj_p in enumerate(adj_p_list):
        all_test_records[i]["p_fdr"] = adj_p
        all_test_records[i]["sig_fdr_05"] = bool(np.isfinite(adj_p) and adj_p <= 0.05)
        all_test_records[i]["sig_fdr_10"] = bool(np.isfinite(adj_p) and adj_p <= 0.10)

    report = {
        "method_version": "pulse-v2.0",
        "analysis_status": "development_reanalysis_not_locked_oos",
        "start": start,
        "end": end,
        "bootstrap_draws": n_perm,
        "seed": seed,
        "total_registered_tests": len(all_test_records),
        "valid_tests": sum(1 for record in all_test_records if record["valid"]),
        "invalid_tests": sum(1 for record in all_test_records if not record["valid"]),
        "provenance": environment_fingerprint(),
        "tests": all_test_records,
    }
    return report


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json_report(report: dict, output: Path) -> str:
    """Write standard JSON plus a detached SHA-256 checksum; return the digest."""
    blob = (json.dumps(_json_safe(report), ensure_ascii=False, indent=2) + "\n").encode()
    digest = hashlib.sha256(blob).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(blob)
    checksum_path = output.with_name(output.name + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return digest


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-04")
    ap.add_argument("--permutations", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    out_default = (
        SERVICE_ROOT / "docs" / "reviews" / "2026-08-04-eleme-v2-draft" / "pulse-v2-results.json"
    )
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    print(f"Hipotez Eleme Tezgâhı çalışıyor... ({args.start} -> {args.end})")
    report = run_workbench(args.start, args.end, args.permutations, args.seed)

    digest = write_json_report(report, args.out)
    print(
        f"Tamamlandı! Toplam test: {report['total_registered_tests']}. "
        f"Çıktı: {args.out} · sha256={digest[:16]}..."
    )


if __name__ == "__main__":
    main()
