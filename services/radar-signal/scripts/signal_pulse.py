"""Kart A nabız teşhisi — sinyalin ÖNGÖRÜ GÜCÜ var mı?

## Soru

S-0002b maliyet sonrası reddedildi (−17 bps/işlem). Ama bu, "sinyalin öngörü gücü yok"
demek değil: sonuç çıkış kuralı, stop, maliyet ve boyutlandırmanın birleşik etkisidir.
Bu script o katmanların HEPSİNİ kaldırır ve tek şeyi sorar:

  **Sinyal barından sonraki ham fiyat hareketi, rastgele bir bardan farklı mı?**

Backtest DEĞİLDİR: emir yok, stop yok, çıkış kuralı yok, maliyet yok, pozisyon yok.
Yalnız "sinyal anı + N bar sonrası" brüt getiri dağılımı.

## Yöntem

1. S-0002b'nin giriş koşulları birebir yeniden üretilir (saat-dilimi koşullamalı rank
   ve medyan, 1h aralık kırılımı, funding %5-95 filtresi).
2. Her sinyal barı için +1/+2/+4/+8/+16 bar ileri BRÜT getiri, **yön düzeltmeli**
   (long: +r, short: −r) hesaplanır.
3. Taban dağılım: aynı dönemin TÜM barları, aynı ufuklar, sinyallerle **aynı yön
   karışımı** kullanılarak.
4. Anlamlılık: permütasyon testi. Aynı sayıda bar rastgele seçilir (aynı yön karışımıyla),
   ortalama hesaplanır, N kez tekrarlanır → gözlenen ortalamanın boş dağılımdaki yeri.
   Dağılım varsayımı yapılmaz; kripto getirileri normal değildir.
5. Kırılımlar: UTC saat dilimi ve volatilite rejimi (ATR persentil terzili).
6. Pencere: 20 gün (koddaki) ve 60 gün (Kart A'nın dediği) yan yana → Ç5 kapanır.

## Yorumlama eşiği

`realistic` senaryoda gidiş-dönüş maliyet ≈ 2 × 8.5 bps = **17 bps**. Brüt ortalama
bunun altındaysa, sinyal istatistiksel olarak anlamlı olsa bile ticari olarak ölüdür.
Script bu eşiği her satırda gösterir.

## Kullanım

    python scripts/signal_pulse.py
    python scripts/signal_pulse.py --permutations 5000 --out docs/reviews/...
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
WINDOWS = {"20g (koddaki)": 80, "60g (Kart A)": 240}
RETURN_PERCENTILE = 0.80
VOLUME_MULT = 1.25
ATR_PERIOD = 14
FUNDING_WINDOW = 1920
ROUNDTRIP_COST_BPS = 17.0  # realistic: 2 × (taker 4.5 + kayma 4.0) bps


def load_pair(symbol: str, start: str, end: str) -> pd.DataFrame:
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


def build_signals(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """S-0002b giriş koşullarını birebir üretir. `direction`: +1 long, −1 short, 0 yok."""
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
        fr_rank = d["funding_rate"].rolling(FUNDING_WINDOW, min_periods=96).rank(pct=True)
        d["funding_ok"] = (fr_rank >= 0.05) & (fr_rank <= 0.95)
    else:
        d["funding_ok"] = True

    vol_ok = d["volume_1h"] >= VOLUME_MULT * d["vol_median"]
    long_sig = (
        (d["rank"] >= RETURN_PERCENTILE) & vol_ok & (d["close"] > d["hmax"]) & d["funding_ok"]
    )
    short_sig = (
        (d["rank"] <= 1 - RETURN_PERCENTILE) & vol_ok & (d["close"] < d["lmin"]) & d["funding_ok"]
    )
    d["direction"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))

    # Volatilite rejimi: ATR'nin kendi geçmişindeki persentili (rejim kırılımı için)
    tr = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - d["close"].shift()).abs(),
            (d["low"] - d["close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr"] = tr.rolling(ATR_PERIOD).mean()
    d["atr_pct"] = d["atr"].rolling(1920, min_periods=240).rank(pct=True)

    for h in HORIZONS:
        d[f"fwd_{h}"] = d["close"].shift(-h) / d["close"] - 1.0
    return d


def permutation_test(
    signal_vals: np.ndarray,
    base: np.ndarray,
    long_share: float,
    n_perm: int,
    rng: np.random.Generator,
) -> dict:
    """Boş dağılım: rastgele bar + rastgele yön (sinyallerle aynı long oranı).

    Yön ataması zaman konumundan BAĞIMSIZ yapılır. İlk sürümde barlar zaman sırasına
    göre ikiye bölünüp ilk parçaya long, kalanına short atanmıştı; bu, dönem içindeki
    fiyat trendini doğrudan tabana sızdırıyordu (taraflı kıyas).

    İki taraflı okuma için hem "sinyal ≥ taban" hem "sinyal ≤ taban" p'si döner:
    ikincisi sinyalin anlamlı biçimde KÖTÜ olup olmadığını söyler.
    """
    n = len(signal_vals)
    if n == 0 or len(base) < 2:
        return {"p_greater": float("nan"), "p_less": float("nan"), "null_mean_bps": float("nan")}
    observed = signal_vals.mean()
    idx = rng.integers(0, len(base), size=(n_perm, n))
    signs = np.where(rng.random((n_perm, n)) < long_share, 1.0, -1.0)
    null_means = (base[idx] * signs).mean(axis=1)
    return {
        "p_greater": float((null_means >= observed).sum() + 1) / (n_perm + 1),
        "p_less": float((null_means <= observed).sum() + 1) / (n_perm + 1),
        "null_mean_bps": float(null_means.mean() * 1e4),
        "null_std_bps": float(null_means.std(ddof=1) * 1e4),
    }


def analyse(d: pd.DataFrame, n_perm: int, rng: np.random.Generator) -> list[dict]:
    rows = []
    sig = d[d["direction"] != 0]
    if sig.empty:
        return rows
    long_share = float((sig["direction"] == 1).mean())

    for h in HORIZONS:
        col = f"fwd_{h}"
        s = sig[[col, "direction"]].dropna()
        if s.empty:
            continue
        signal_vals = (s[col] * s["direction"]).to_numpy()
        base = d[[col]].dropna()[col].to_numpy()
        test = permutation_test(signal_vals, base, long_share, n_perm, rng)
        mean_bps = float(signal_vals.mean() * 1e4)
        rows.append(
            {
                "horizon_bars": h,
                "horizon_min": h * 15,
                "n_signals": int(len(signal_vals)),
                "mean_bps": mean_bps,
                "median_bps": float(np.median(signal_vals) * 1e4),
                "hit_rate": float((signal_vals > 0).mean()),
                "std_bps": float(signal_vals.std(ddof=1) * 1e4),
                "null_mean_bps": test["null_mean_bps"],
                "null_std_bps": test.get("null_std_bps"),
                "edge_vs_null_bps": mean_bps - test["null_mean_bps"],
                "p_greater": test["p_greater"],
                "p_less": test["p_less"],
                "beats_cost": bool(mean_bps > ROUNDTRIP_COST_BPS),
            }
        )
    return rows


def breakdown(d: pd.DataFrame, horizon: int, by: str) -> list[dict]:
    col = f"fwd_{horizon}"
    sig = d[(d["direction"] != 0)][[col, "direction", "hour", "atr_pct"]].dropna()
    if sig.empty:
        return []
    sig = sig.assign(adj=sig[col] * sig["direction"])
    if by == "hour":
        sig = sig.assign(
            bucket=pd.cut(
                sig["hour"], [-1, 5, 11, 17, 23], labels=["00-05", "06-11", "12-17", "18-23"]
            )
        )
    else:
        sig = sig.assign(
            bucket=pd.cut(
                sig["atr_pct"],
                [0, 1 / 3, 2 / 3, 1.0],
                labels=["düşük vol", "orta vol", "yüksek vol"],
            )
        )
    out = []
    for name, g in sig.groupby("bucket", observed=True):
        out.append(
            {
                "bucket": str(name),
                "n": int(len(g)),
                "mean_bps": float(g["adj"].mean() * 1e4),
                "hit_rate": float((g["adj"] > 0).mean()),
            }
        )
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--permutations", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    report: dict = {
        "period": [args.start, args.end],
        "permutations": args.permutations,
        "seed": args.seed,
        "roundtrip_cost_bps": ROUNDTRIP_COST_BPS,
        "results": {},
    }

    for symbol in ("BTC", "ETH"):
        df = load_pair(symbol, args.start, args.end)
        for wname, window in WINDOWS.items():
            d = build_signals(df, window)
            key = f"{symbol} · {wname}"
            rows = analyse(d, args.permutations, rng)
            report["results"][key] = {
                "bars": int(len(d)),
                "signals": int((d["direction"] != 0).sum()),
                "long_share": float(
                    (d["direction"] == 1).sum() / max(1, (d["direction"] != 0).sum())
                ),
                "horizons": rows,
                "by_hour_h4": breakdown(d, 4, "hour"),
                "by_vol_h4": breakdown(d, 4, "vol"),
            }

            print(f"\n{'=' * 84}\n{key}   ({len(d)} bar, {(d['direction'] != 0).sum()} sinyal)")
            print(
                f"{'ufuk':>7} {'n':>6} {'ort bps':>9} {'medyan':>8} {'isabet':>7} "
                f"{'boş ort':>8} {'fark':>8} {'p(iyi)':>7} {'p(kötü)':>8} {'maliyet':>8}"
            )
            for r in rows:
                print(
                    f"{r['horizon_bars']:>5}bar {r['n_signals']:>6} {r['mean_bps']:>9.2f} "
                    f"{r['median_bps']:>8.2f} {r['hit_rate']:>6.1%} "
                    f"{r['null_mean_bps']:>8.2f} {r['edge_vs_null_bps']:>8.2f} "
                    f"{r['p_greater']:>7.3f} {r['p_less']:>8.3f} "
                    f"{'GEÇTİ' if r['beats_cost'] else 'hayır':>8}"
                )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {args.out}")


if __name__ == "__main__":
    main()
