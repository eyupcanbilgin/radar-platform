"""Download public, closed Bybit BTCUSDT perpetual 1h candles into the ignored user_data tree.

Why a second derivatives venue: the pre-registration cards require a venue-robustness gate
(`evaluate_period_venue_fragility`), but with a single execution venue that gate could never
run — S-0005 and S-0006 both had to report it ``not_evaluated``.  A criterion that can never
be evaluated is not a criterion.

Why Bybit specifically, and why not the other candidates (measured 2026-08-10, not assumed):

- Binance ``futures/data`` endpoints (``takerlongshortRatio``,
  ``globalLongShortAccountRatio``, ``topLongShortPositionRatio``) reject a 2024 ``startTime``
  with ``-1130``; they retain roughly 30 days, exactly like ``openInterestHist``.  They are
  dead ends for Development-window research.
- Bybit v5 ``market/kline`` and ``market/funding/history`` both return real 2024 data.

So Bybit is the only new *historical* surface available, and SPEC §2.1 already lists it as
the planned cross-validation venue.

Paging, completeness and gap reporting are not reimplemented: this reuses the same verified
helpers as the Coinbase and Binance spot downloaders, so every venue in the manifest is built
by identical rules.
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
    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    frame = fetch_closed_candles(
        exchange,
        since_ms=_ms(args.start),
        until_ms=_ms(args.end),
        symbol="BTC/USDT:USDT",
        venue="Bybit perp",
    )
    destination = market_data_root() / "bybit" / "futures" / "BTC_USDT_USDT-1h-futures.feather"
    write_atomic(frame, destination)
    coverage = frame.attrs["coverage"]
    print(
        f"OK: {destination} · {len(frame)} kapalı mum · "
        f"{coverage['missing_hours']} eksik saat/{len(coverage['gaps'])} gap"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
