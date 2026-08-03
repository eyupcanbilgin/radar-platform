"""Backtest sarmalayıcısı — TEK meşru backtest giriş noktası.

Zorunluluklar (CLAUDE.md):
- Kural 6: maliyetsiz koşu yok; senaryo adı çıktıda ve kayıtta. `--timeframe-detail 1m`
  varsayılan; kapatmak için --no-detail + gerekçe zorunlu (kayda geçer).
- Kural 8: her koşu Experiment Registry'ye yazılır; registry yazılamazsa koşu geçersizdir.

Kullanım:
    .venv/Scripts/python scripts/bt.py --strategy S0001EmaCross --hypothesis S-0001
    .venv/Scripts/python scripts/bt.py --strategy S0001EmaCross --hypothesis S-0001 \\
        --scenario taker_heavy --timerange 20250101-20250701
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from costslib import costs_hash, effective_fee, load_costs  # noqa: E402
from registrylib import record_run  # noqa: E402

FREQTRADE = REPO / ".venv" / "Scripts" / "freqtrade"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--hypothesis", required=True, help="Hipotez kartı kimliği (ör. S-0001)")
    ap.add_argument(
        "--scenario", default="realistic", help="CR-5 senaryo adı (varsayılan: realistic)"
    )
    ap.add_argument("--timerange", default=None)
    ap.add_argument("--pairs", nargs="*", default=None)
    ap.add_argument("--timeframe-detail", default="1m")
    ap.add_argument(
        "--no-detail", action="store_true", help="1m detayı kapat (gerekçe --reason ile zorunlu)"
    )
    ap.add_argument("--reason", default=None, help="--no-detail gerekçesi")
    ap.add_argument(
        "--dry-print", action="store_true", help="freqtrade'i çalıştırmadan komutu yazdır (test)"
    )
    args = ap.parse_args()

    if args.no_detail and not args.reason:
        sys.exit("HATA: --no-detail için --reason zorunlu (kural 6; kayda geçer)")

    costs = load_costs()
    fee = effective_fee(costs, args.scenario)

    cmd = [
        str(FREQTRADE),
        "backtesting",
        "--userdir",
        "user_data",
        "--config",
        "config/config.dryrun.json",
        "--strategy",
        args.strategy,
        "--fee",
        f"{fee:.6f}",
        "--export",
        "trades",
    ]
    if not args.no_detail:
        cmd += ["--timeframe-detail", args.timeframe_detail]
    if args.timerange:
        cmd += ["--timerange", args.timerange]
    if args.pairs:
        cmd += ["--pairs", *args.pairs]

    print(f"[bt] senaryo={args.scenario} efektif_fee={fee:.6f} costs_hash={costs_hash()}")
    if args.dry_print:
        print("[bt] komut:", " ".join(cmd))
        return

    proc = subprocess.run(cmd, cwd=REPO)
    record_run(
        strategy=args.strategy,
        hypothesis_id=args.hypothesis,
        scenario=args.scenario,
        effective_fee=fee,
        timerange=args.timerange,
        timeframe_detail=None if args.no_detail else args.timeframe_detail,
        no_detail_reason=args.reason,
        exit_code=proc.returncode,
    )
    if proc.returncode != 0:
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
