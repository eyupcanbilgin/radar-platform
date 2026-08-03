"""Intra-candle Execution Drift raporu — CR-002 P0-5.

Soru: işlemlerin ne kadarı 15m mum kapanışında değil, mum İÇİNDE (1m detay yolundan)
kapandı ve bunların P&L etkisi ne? Bu oran yükseldikçe canlı-backtest tutarlılığı
1m detay simülasyonunun kalitesine daha çok bağımlı hale gelir — yani sonucun
kırılganlığı artar. Rapor bunu görünür kılar; gizlenirse "backtest gerçeği yansıtıyor"
sanılır.

Kullanım:
    .venv/Scripts/python scripts/drift_report.py                 # en son koşu
    .venv/Scripts/python scripts/drift_report.py --result <zip>
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO / "user_data" / "backtest_results"
TIMEFRAME_MINUTES = 15


def latest_result() -> Path:
    results = sorted(RESULTS_DIR.glob("backtest-result-*.zip"))
    if not results:
        sys.exit("HATA: backtest sonucu yok; önce scripts/bt.py koş")
    return results[-1]


def load_trades(path: Path) -> pd.DataFrame:
    from freqtrade.data.btanalysis import load_backtest_data

    return load_backtest_data(path)


def analyse(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0}
    close_min = pd.to_datetime(trades["close_date"]).dt.minute
    # Mum kapanışında kapananlar: dakika 15'in katı VE saniye 0
    on_grid = (close_min % TIMEFRAME_MINUTES == 0) & (
        pd.to_datetime(trades["close_date"]).dt.second == 0
    )
    intracandle = ~on_grid
    total = len(trades)
    profit_col = "profit_abs" if "profit_abs" in trades else "profit_ratio"
    return {
        "trades": total,
        "intracandle_exits": int(intracandle.sum()),
        "intracandle_share_pct": round(100.0 * intracandle.sum() / total, 2),
        "pnl_intracandle": round(float(trades.loc[intracandle, profit_col].sum()), 4),
        "pnl_on_candle_close": round(float(trades.loc[on_grid, profit_col].sum()), 4),
        "exit_reasons_intracandle": (
            trades.loc[intracandle, "exit_reason"].value_counts().to_dict()
            if "exit_reason" in trades
            else {}
        ),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", type=Path, default=None)
    args = ap.parse_args()

    path = args.result or latest_result()
    stats = analyse(load_trades(path))
    print(f"Intra-candle Execution Drift · kaynak: {path.name}\n")
    if stats["trades"] == 0:
        print("İşlem yok.")
        return
    print(f"  Toplam işlem                : {stats['trades']}")
    print(
        f"  Mum İÇİNDE kapanan          : {stats['intracandle_exits']} "
        f"(%{stats['intracandle_share_pct']})"
    )
    print(f"  P&L (mum içi çıkışlar)      : {stats['pnl_intracandle']}")
    print(f"  P&L (mum kapanışı çıkışları): {stats['pnl_on_candle_close']}")
    if stats["exit_reasons_intracandle"]:
        print("  Mum içi çıkış sebepleri     :")
        for reason, count in sorted(stats["exit_reasons_intracandle"].items()):
            print(f"      {reason:24} {count}")
    print(
        "\nNot: Mum içi çıkış oranı yükseldikçe sonuç 1m simülasyon kalitesine daha bağımlıdır;\n"
        "aynı 1m mumda stop ve hedef birlikte görülüyorsa STOP önce sayılır (CR-002 P0-5)."
    )


if __name__ == "__main__":
    main()
