"""Hipotez Eleme Tezgâhı — Hipotez Kartları (A, B, C, D, E, I, J, K, L, M) Nabız Teşhis Motoru.

Bu script, strateji kodu yazılmadan önce tüm test edilebilir hipotez kartlarının ham öngörü
gücünü (yönsel getiri beklentisi ve volatilite genişleme oranı) ölçer.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))
from datapaths import data_dir  # noqa: E402

HORIZONS = (1, 2, 4, 8, 16)
ROUNDTRIP_COST_BPS_BTC = 17.0
ROUNDTRIP_COST_BPS_ETH = 20.0


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg False Discovery Rate (FDR) p-değeri düzeltmesi."""
    n = len(p_values)
    if n == 0:
        return []
    valid_p = [(i, p) for i, p in enumerate(p_values) if not np.isnan(p)]
    if not valid_p:
        return [float("nan")] * n

    valid_p.sort(key=lambda x: x[1])
    adjusted = [1.0] * len(valid_p)
    cum_min = 1.0

    for rank_idx in range(len(valid_p) - 1, -1, -1):
        orig_idx, p = valid_p[rank_idx]
        rank = rank_idx + 1
        adj_p = min(cum_min, (p * n) / rank)
        cum_min = adj_p
        adjusted[rank_idx] = min(1.0, max(0.0, adj_p))

    res = [float("nan")] * n
    for rank_idx, (orig_idx, _) in enumerate(valid_p):
        res[orig_idx] = float(adjusted[rank_idx])
    return res


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


def permutation_test(
    signal_vals: np.ndarray,
    base: np.ndarray,
    long_share: float,
    n_perm: int,
    rng: np.random.Generator,
    mode: str = "directional",
) -> dict:
    n = len(signal_vals)
    if n == 0 or len(base) < 2:
        return {"p_greater": float("nan"), "p_less": float("nan"), "null_mean": float("nan")}

    observed = float(signal_vals.mean())
    idx = rng.integers(0, len(base), size=(n_perm, n))

    if mode == "directional":
        signs = np.where(rng.random((n_perm, n)) < long_share, 1.0, -1.0)
        null_means = (base[idx] * signs).mean(axis=1)
    else:  # volatility ratio mode
        null_means = base[idx].mean(axis=1)

    p_greater = float((null_means >= observed).sum() + 1) / (n_perm + 1)
    p_less = float((null_means <= observed).sum() + 1) / (n_perm + 1)

    return {
        "p_greater": p_greater,
        "p_less": p_less,
        "null_mean": float(null_means.mean()),
        "null_std": float(null_means.std(ddof=1)),
    }


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

    for h in HORIZONS:
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
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

    for h in HORIZONS:
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
    return d


def build_signals_card_c(df: pd.DataFrame) -> pd.DataFrame:
    """Kart C — AB/ABD Seansı (12:00-20:00 UTC) ilk 30m -> son momentum."""
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["minute"] = d["date"].dt.minute

    is_session_open_eval = (d["hour"] == 12) & (d["minute"] == 30)
    ret_first_30m = d["close"] / d["close"].shift(2) - 1.0
    vol_first_30m = d["volume"].rolling(2).sum()
    vol_30m_p70 = vol_first_30m.rolling(90 * 96, min_periods=10).quantile(0.70)

    sig_long = is_session_open_eval & (ret_first_30m > 0) & (vol_first_30m > vol_30m_p70)
    sig_short = is_session_open_eval & (ret_first_30m < 0) & (vol_first_30m > vol_30m_p70)

    d["direction"] = np.where(sig_long, 1, np.where(sig_short, -1, 0))

    for h in (2, 4, 16):  # 13:30, 14:30, 20:30 UTC
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
    return d


def build_signals_card_d(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Kart D — 15m mum sınırı anomalisi (1m veri ile)."""
    d = df_1m.copy()
    d["minute"] = d["date"].dt.minute
    d["is_boundary"] = d["minute"].isin([59, 0, 14, 15, 29, 30, 44, 45])
    d["fwd_1m"] = d["close"].shift(-1) / d["close"] - 1.0
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
    d["direction"] = np.where(high_funding, 1, 0)

    for h in (4, 8, 16):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        ret_short = d["close"].pct_change()
        rv_post = ret_short.shift(-h).rolling(h).std()
        rv_base = ret_short.rolling(96).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_base)
    return d


def build_signals_card_i(df: pd.DataFrame, session: str) -> pd.DataFrame:
    """Kart I — Londra (08:00 UTC) veya NY (14:00 UTC) açılışı ORB & Volatilite."""
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["minute"] = d["date"].dt.minute

    target_hour = 8 if session == "london" else 14
    is_eval_bar = (d["hour"] == target_hour) & (d["minute"] == 15)

    pre_high = d["high"].shift(1).rolling(4).max()
    pre_low = d["low"].shift(1).rolling(4).min()

    long_orb = is_eval_bar & (d["close"] > pre_high)
    short_orb = is_eval_bar & (d["close"] < pre_low)
    d["direction"] = np.where(long_orb, 1, np.where(short_orb, -1, 0))
    d["event_trigger"] = np.where(is_eval_bar, 1, 0)

    for h in (1, 2, 4):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        ret_15m = d["close"].pct_change()
        rv_post = ret_15m.shift(-h).rolling(h).std()
        rv_pre = ret_15m.rolling(4).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_pre)
    return d


def build_signals_card_j(df: pd.DataFrame) -> pd.DataFrame:
    """Kart J — Hafta sonu geçişi volatilite ve breakout."""
    d = df.copy()
    d["dayofweek"] = d["date"].dt.dayofweek
    d["is_weekend"] = d["dayofweek"].isin([5, 6])

    hmax_4h = d["high"].shift(1).rolling(16).max()
    lmin_4h = d["low"].shift(1).rolling(16).min()
    long_sig = d["is_weekend"] & (d["close"] > hmax_4h)
    short_sig = d["is_weekend"] & (d["close"] < lmin_4h)

    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    d["event_trigger"] = np.where(d["is_weekend"], 1, 0)

    for h in (1, 2, 4, 8):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        ret_15m = d["close"].pct_change()
        rv_post = ret_15m.shift(-h).rolling(h).std()
        rv_base = ret_15m.rolling(96).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_base)
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

    for h in (1, 2, 4):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        ret_15m = d["close"].pct_change()
        rv_post = ret_15m.shift(-h).rolling(h).std()
        rv_base = ret_15m.rolling(96).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_base)
    return d


def build_signals_card_l(df: pd.DataFrame) -> pd.DataFrame:
    """Kart L — Volatilite kümelenmesi (`RV_short / RV_long`) rejim devamı."""
    d = df.copy()
    ret_15m = d["close"].pct_change()
    rv_short = ret_15m.rolling(4).std()
    rv_long = ret_15m.rolling(96).std()
    regime_ratio = rv_short / np.maximum(1e-6, rv_long)

    high_vol_regime = regime_ratio > regime_ratio.rolling(1920, min_periods=240).quantile(0.80)

    hmax_4h = d["high"].shift(1).rolling(16).max()
    lmin_4h = d["low"].shift(1).rolling(16).min()
    long_sig = high_vol_regime & (d["close"] > hmax_4h)
    short_sig = high_vol_regime & (d["close"] < lmin_4h)

    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    d["event_trigger"] = np.where(high_vol_regime, 1, 0)

    for h in (4, 8, 16):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        rv_post = ret_15m.shift(-h).rolling(h).std()
        rv_base = ret_15m.rolling(96).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_base)
    return d


def build_signals_card_m(df: pd.DataFrame) -> pd.DataFrame:
    """Kart M — Deribit settlement 08:00 UTC aktivitesi."""
    d = df.copy()
    d["hour"] = d["date"].dt.hour
    d["minute"] = d["date"].dt.minute

    is_0800_bar = (d["hour"] == 8) & (d["minute"] == 0)
    is_eval_bar = (d["hour"] == 8) & (d["minute"] == 15)

    ret_0800 = d["close"] / d["close"].shift(1) - 1.0
    sig_long = is_eval_bar & (ret_0800 > 0)
    sig_short = is_eval_bar & (ret_0800 < 0)

    d["direction"] = np.where(sig_long, 1, np.where(sig_short, -1, 0))
    d["event_trigger"] = np.where(is_0800_bar, 1, 0)

    for h in (1, 2, 4):
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
        ret_15m = d["close"].pct_change()
        rv_post = ret_15m.shift(-h).rolling(h).std()
        rv_base = ret_15m.rolling(96).std()
        d[f"vol_ratio_{h}"] = rv_post / np.maximum(1e-6, rv_base)
    return d


# =====================================================================
# ELEME BENCHMARK ÇALIŞTIRICI
# =====================================================================

def run_workbench(
    start: str = "2024-01-01",
    end: str = "2026-08-03",
    n_perm: int = 2000,
    seed: int = 20260804,
) -> dict:
    rng = np.random.default_rng(seed)
    fomc_df = load_fomc_calendar()
    all_test_records = []

    for symbol in ("BTC", "ETH"):
        cost_th = ROUNDTRIP_COST_BPS_BTC if symbol == "BTC" else ROUNDTRIP_COST_BPS_ETH
        df_15m = load_pair_15m(symbol, start, end)
        df_1m = load_pair_1m(symbol, start, end)

        # Kart A
        for wname, wval in [("20g", 80), ("60g", 240)]:
            da = build_signals_card_a(df_15m, wval)
            sig = da[da["direction"] != 0]
            long_share = float((sig["direction"] == 1).mean()) if not sig.empty else 0.5
            base = da["fwd_4"].dropna().to_numpy()
            for h in (1, 2, 4, 8, 16):
                col = f"fwd_{h}"
                s = da[da["direction"] != 0][[col, "direction"]].dropna()
                signal_vals = (s[col] * s["direction"]).to_numpy()
                test = permutation_test(
                    signal_vals, base, long_share, n_perm, rng, mode="directional"
                )
                mean_bps = float(signal_vals.mean() * 1e4) if len(signal_vals) > 0 else 0.0
                all_test_records.append({
                    "card": "A", "variant": f"Kart A ({wname})", "symbol": symbol,
                    "horizon": f"+{h}bar", "mode": "directional",
                    "n_signals": len(signal_vals), "mean_bps": mean_bps,
                    "hit_rate": float((signal_vals > 0).mean()) if len(signal_vals) > 0 else 0.0,
                    "p_raw": test["p_less"] if mean_bps < 0 else test["p_greater"],
                    "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
                })

        # Kart B
        db = build_signals_card_b(df_15m)
        sig_b = db[db["direction"] != 0]
        long_share_b = float((sig_b["direction"] == 1).mean()) if not sig_b.empty else 0.5
        base_b = db["fwd_4"].dropna().to_numpy()
        for h in (1, 2, 4, 8, 16):
            col = f"fwd_{h}"
            s = db[db["direction"] != 0][[col, "direction"]].dropna()
            signal_vals = (s[col] * s["direction"]).to_numpy()
            test = permutation_test(
                signal_vals, base_b, long_share_b, n_perm, rng, mode="directional"
            )
            mean_bps = float(signal_vals.mean() * 1e4) if len(signal_vals) > 0 else 0.0
            all_test_records.append({
                "card": "B", "variant": "Kart B (Jump-reversal)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(signal_vals), "mean_bps": mean_bps,
                "hit_rate": float((signal_vals > 0).mean()) if len(signal_vals) > 0 else 0.0,
                "p_raw": test["p_less"] if mean_bps < 0 else test["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart C
        dc = build_signals_card_c(df_15m)
        sig_c = dc[dc["direction"] != 0]
        long_share_c = float((sig_c["direction"] == 1).mean()) if not sig_c.empty else 0.5
        base_c = dc["fwd_4"].dropna().to_numpy()
        for h in (2, 4, 16):
            col = f"fwd_{h}"
            s = dc[dc["direction"] != 0][[col, "direction"]].dropna()
            signal_vals = (s[col] * s["direction"]).to_numpy()
            test = permutation_test(
                signal_vals, base_c, long_share_c, n_perm, rng, mode="directional"
            )
            mean_bps = float(signal_vals.mean() * 1e4) if len(signal_vals) > 0 else 0.0
            all_test_records.append({
                "card": "C", "variant": "Kart C (Seans momentum)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(signal_vals), "mean_bps": mean_bps,
                "hit_rate": float((signal_vals > 0).mean()) if len(signal_vals) > 0 else 0.0,
                "p_raw": test["p_less"] if mean_bps < 0 else test["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart D (1m)
        dd = build_signals_card_d(df_1m)
        b_vals = dd[dd["is_boundary"]]["fwd_1m"].dropna().to_numpy()
        nb_vals = dd[~dd["is_boundary"]]["fwd_1m"].dropna().to_numpy()
        test_d = permutation_test(b_vals, nb_vals, 0.5, n_perm, rng, mode="volatility")
        mean_b_bps = float(b_vals.mean() * 1e4)
        all_test_records.append({
            "card": "D", "variant": "Kart D (15m mum sınırı 1m)", "symbol": symbol,
            "horizon": "+1m", "mode": "directional", "n_signals": len(b_vals),
            "mean_bps": mean_b_bps, "hit_rate": float((b_vals > 0).mean()),
            "p_raw": test_d["p_greater"], "cost_threshold_bps": cost_th,
            "beats_cost": mean_b_bps > cost_th
        })

        # Kart E
        de = build_signals_card_e(df_15m)
        sig_e = de[de["direction"] == 1]
        base_e = de["fwd_4"].dropna().to_numpy()
        for h in (4, 8, 16):
            col_ret, col_vol = f"fwd_{h}", f"vol_ratio_{h}"
            vol_vals = sig_e[col_vol].dropna().to_numpy()
            base_vol = de[col_vol].dropna().to_numpy()
            test_vol = permutation_test(vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility")
            vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
            all_test_records.append({
                "card": "E", "variant": "Kart E (Excess funding vol ratio)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "volatility_ratio",
                "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                "beats_cost": vol_ratio_mean > 1.0
            })
            ret_vals = sig_e[col_ret].dropna().to_numpy()
            test_ret = permutation_test(ret_vals, base_e, 0.5, n_perm, rng, mode="directional")
            mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
            all_test_records.append({
                "card": "E", "variant": "Kart E (Excess funding return)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(ret_vals), "mean_bps": mean_bps,
                "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart I (London & NY)
        for sname in ("london", "ny"):
            di = build_signals_card_i(df_15m, sname)
            sig_i = di[di["direction"] != 0]
            long_share_i = float((sig_i["direction"] == 1).mean()) if not sig_i.empty else 0.5
            base_i = di["fwd_4"].dropna().to_numpy()
            for h in (1, 2, 4):
                col_vol, col_ret = f"vol_ratio_{h}", f"fwd_{h}"
                vol_vals = di[di["event_trigger"] == 1][col_vol].dropna().to_numpy()
                base_vol = di[col_vol].dropna().to_numpy()
                test_vol = permutation_test(
                    vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility"
                )
                vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
                all_test_records.append({
                    "card": "I", "variant": f"Kart I ({sname} vol ratio)", "symbol": symbol,
                    "horizon": f"+{h}bar", "mode": "volatility_ratio",
                    "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                    "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                    "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                    "beats_cost": vol_ratio_mean > 1.0
                })
                s_ret = sig_i[[col_ret, "direction"]].dropna()
                ret_vals = (s_ret[col_ret] * s_ret["direction"]).to_numpy()
                test_ret = permutation_test(
                    ret_vals, base_i, long_share_i, n_perm, rng, mode="directional"
                )
                mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
                all_test_records.append({
                    "card": "I", "variant": f"Kart I ({sname} ORB return)", "symbol": symbol,
                    "horizon": f"+{h}bar", "mode": "directional",
                    "n_signals": len(ret_vals), "mean_bps": mean_bps,
                    "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                    "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                    "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
                })

        # Kart J
        dj = build_signals_card_j(df_15m)
        sig_j = dj[dj["direction"] != 0]
        long_share_j = float((sig_j["direction"] == 1).mean()) if not sig_j.empty else 0.5
        base_j = dj["fwd_4"].dropna().to_numpy()
        for h in (1, 2, 4, 8):
            col_vol, col_ret = f"vol_ratio_{h}", f"fwd_{h}"
            vol_vals = dj[dj["event_trigger"] == 1][col_vol].dropna().to_numpy()
            base_vol = dj[col_vol].dropna().to_numpy()
            test_vol = permutation_test(vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility")
            vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
            all_test_records.append({
                "card": "J", "variant": "Kart J (Weekend vol ratio)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "volatility_ratio",
                "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                "beats_cost": vol_ratio_mean > 1.0
            })
            s_ret = sig_j[[col_ret, "direction"]].dropna()
            ret_vals = (s_ret[col_ret] * s_ret["direction"]).to_numpy()
            test_ret = permutation_test(
                ret_vals, base_j, long_share_j, n_perm, rng, mode="directional"
            )
            mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
            all_test_records.append({
                "card": "J", "variant": "Kart J (Weekend breakout return)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(ret_vals), "mean_bps": mean_bps,
                "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart K (FOMC)
        dk = build_signals_card_k(df_15m, fomc_df)
        sig_k = dk[dk["direction"] != 0]
        long_share_k = float((sig_k["direction"] == 1).mean()) if not sig_k.empty else 0.5
        base_k = dk["fwd_4"].dropna().to_numpy()
        for h in (1, 2, 4):
            col_vol, col_ret = f"vol_ratio_{h}", f"fwd_{h}"
            vol_vals = dk[dk["event_trigger"] == 1][col_vol].dropna().to_numpy()
            base_vol = dk[col_vol].dropna().to_numpy()
            test_vol = permutation_test(vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility")
            vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
            all_test_records.append({
                "card": "K", "variant": "Kart K (FOMC vol ratio)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "volatility_ratio",
                "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                "beats_cost": vol_ratio_mean > 1.0
            })
            s_ret = sig_k[[col_ret, "direction"]].dropna()
            ret_vals = (s_ret[col_ret] * s_ret["direction"]).to_numpy()
            test_ret = permutation_test(
                ret_vals, base_k, long_share_k, n_perm, rng, mode="directional"
            )
            mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
            all_test_records.append({
                "card": "K", "variant": "Kart K (FOMC ORB return)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(ret_vals), "mean_bps": mean_bps,
                "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart L
        dl = build_signals_card_l(df_15m)
        sig_l = dl[dl["direction"] != 0]
        long_share_l = float((sig_l["direction"] == 1).mean()) if not sig_l.empty else 0.5
        base_l = dl["fwd_4"].dropna().to_numpy()
        for h in (4, 8, 16):
            col_vol, col_ret = f"vol_ratio_{h}", f"fwd_{h}"
            vol_vals = dl[dl["event_trigger"] == 1][col_vol].dropna().to_numpy()
            base_vol = dl[col_vol].dropna().to_numpy()
            test_vol = permutation_test(vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility")
            vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
            all_test_records.append({
                "card": "L", "variant": "Kart L (Vol clustering ratio)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "volatility_ratio",
                "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                "beats_cost": vol_ratio_mean > 1.0
            })
            s_ret = sig_l[[col_ret, "direction"]].dropna()
            ret_vals = (s_ret[col_ret] * s_ret["direction"]).to_numpy()
            test_ret = permutation_test(
                ret_vals, base_l, long_share_l, n_perm, rng, mode="directional"
            )
            mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
            all_test_records.append({
                "card": "L", "variant": "Kart L (Vol clustering momentum)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(ret_vals), "mean_bps": mean_bps,
                "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

        # Kart M
        dm = build_signals_card_m(df_15m)
        sig_m = dm[dm["direction"] != 0]
        long_share_m = float((sig_m["direction"] == 1).mean()) if not sig_m.empty else 0.5
        base_m = dm["fwd_4"].dropna().to_numpy()
        for h in (1, 2, 4):
            col_vol, col_ret = f"vol_ratio_{h}", f"fwd_{h}"
            vol_vals = dm[dm["event_trigger"] == 1][col_vol].dropna().to_numpy()
            base_vol = dm[col_vol].dropna().to_numpy()
            test_vol = permutation_test(vol_vals, base_vol, 0.5, n_perm, rng, mode="volatility")
            vol_ratio_mean = float(vol_vals.mean()) if len(vol_vals) > 0 else 1.0
            all_test_records.append({
                "card": "M", "variant": "Kart M (08:00 UTC vol ratio)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "volatility_ratio",
                "n_signals": len(vol_vals), "mean_bps": (vol_ratio_mean - 1.0) * 100,
                "hit_rate": float((vol_vals > 1.0).mean()) if len(vol_vals) > 0 else 0.0,
                "p_raw": test_vol["p_greater"], "cost_threshold_bps": 0.0,
                "beats_cost": vol_ratio_mean > 1.0
            })
            s_ret = sig_m[[col_ret, "direction"]].dropna()
            ret_vals = (s_ret[col_ret] * s_ret["direction"]).to_numpy()
            test_ret = permutation_test(
                ret_vals, base_m, long_share_m, n_perm, rng, mode="directional"
            )
            mean_bps = float(ret_vals.mean() * 1e4) if len(ret_vals) > 0 else 0.0
            all_test_records.append({
                "card": "M", "variant": "Kart M (08:00 UTC return)", "symbol": symbol,
                "horizon": f"+{h}bar", "mode": "directional",
                "n_signals": len(ret_vals), "mean_bps": mean_bps,
                "hit_rate": float((ret_vals > 0).mean()) if len(ret_vals) > 0 else 0.0,
                "p_raw": test_ret["p_less"] if mean_bps < 0 else test_ret["p_greater"],
                "cost_threshold_bps": cost_th, "beats_cost": mean_bps > cost_th
            })

    raw_p_list = [r["p_raw"] for r in all_test_records]
    adj_p_list = benjamini_hochberg(raw_p_list)

    for i, adj_p in enumerate(adj_p_list):
        all_test_records[i]["p_fdr"] = adj_p
        all_test_records[i]["sig_fdr_05"] = bool(adj_p <= 0.05)
        all_test_records[i]["sig_fdr_10"] = bool(adj_p <= 0.10)

    report = {
        "start": start, "end": end, "permutations": n_perm, "seed": seed,
        "total_registered_tests": len(all_test_records),
        "tests": all_test_records
    }
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--permutations", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    out_default = (
        SERVICE_ROOT / "docs" / "reviews" / "2026-08-04-eleme" / "eleme-sonuclari.json"
    )
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    print(f"Hipotez Eleme Tezgâhı çalışıyor... ({args.start} -> {args.end})")
    report = run_workbench(args.start, args.end, args.permutations, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tamamlandı! Toplam test: {report['total_registered_tests']}. Çıktı: {args.out}")


if __name__ == "__main__":
    main()
