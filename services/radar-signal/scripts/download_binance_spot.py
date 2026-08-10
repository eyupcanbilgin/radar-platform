"""Download public, closed Binance BTC/USDT 1h SPOT candles into the ignored user_data tree.

S-0005 needs the *spot* leg of the Coinbase premium.  The repository already stores Binance
**perpetual** OHLCV, but measuring the premium against the perp would fold funding/basis —
i.e. the S-0003 mechanism — back into a hypothesis that is pre-registered as independent of
derivatives.  Spot-versus-spot keeps that independence intact.

Paging, completeness and gap reporting are deliberately NOT reimplemented here: this reuses
the same verified helpers as the Coinbase downloader, so both legs of the premium are built
by identical rules and a bug cannot silently affect only one side.
"""

import argparse
import sys
from pathlib import Path

import ccxt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datapaths import market_data_root  # noqa: E402
from download_coinbase_spot import (  # noqa: E402
    DEFAULT_START,
    _ms,
    fetch_closed_candles,
    write_atomic,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument(
        "--end",
        required=True,
        help="exclusive UTC boundary; Locked OOS için 2026-08-04T00:00:00Z",
    )
    args = parser.parse_args(argv)
    exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    frame = fetch_closed_candles(
        exchange,
        since_ms=_ms(args.start),
        until_ms=_ms(args.end),
        symbol="BTC/USDT",
        venue="Binance spot",
    )
    destination = market_data_root() / "binance" / "spot" / "BTC_USDT-1h-spot.feather"
    write_atomic(frame, destination)
    coverage = frame.attrs["coverage"]
    print(
        f"OK: {destination} · {len(frame)} kapalı mum · "
        f"{coverage['missing_hours']} eksik saat/{len(coverage['gaps'])} gap"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
