"""Download public, closed Coinbase BTC/USD 1h candles into the ignored user_data tree."""

import argparse
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datapaths import market_data_root  # noqa: E402

TIMEFRAME_MS = 3_600_000
DEFAULT_START = "2024-01-01T00:00:00Z"


def _ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("tarih timezone-aware olmalı")
    return int(parsed.astimezone(UTC).timestamp() * 1000)


def hourly_gaps(timestamps: list[int]) -> list[dict]:
    gaps = []
    for left, right in zip(timestamps, timestamps[1:], strict=False):
        delta = right - left
        if delta != TIMEFRAME_MS:
            gaps.append(
                {
                    "after_utc": pd.to_datetime(left, unit="ms", utc=True).isoformat(),
                    "before_utc": pd.to_datetime(right, unit="ms", utc=True).isoformat(),
                    "missing_hours": delta // TIMEFRAME_MS - 1,
                }
            )
    return gaps


def fetch_closed_candles(
    exchange,
    *,
    since_ms: int,
    until_ms: int,
    symbol: str = "BTC/USD",
    venue: str = "Coinbase",
) -> pd.DataFrame:
    """Fetch an exact, fully closed hourly range or fail loudly.

    ``symbol``/``venue`` default to the Coinbase spot leg so existing callers are
    unchanged; the Binance spot downloader reuses this same verified paging and
    completeness logic instead of copying it (S-0005 needs both legs).
    """
    if until_ms <= since_ms:
        raise ValueError("until, since sonrasında olmalı")
    rows = []
    cursor = since_ms
    while cursor < until_ms:
        page = exchange.fetch_ohlcv(symbol, "1h", since=cursor, limit=300)
        if not page:
            break
        accepted = [
            row for row in page if cursor <= int(row[0]) and int(row[0]) + TIMEFRAME_MS <= until_ms
        ]
        rows.extend(accepted)
        next_cursor = int(page[-1][0]) + TIMEFRAME_MS
        if next_cursor <= cursor:
            raise ValueError(f"{venue} pagination ilerlemedi")
        cursor = next_cursor
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if frame.empty:
        raise ValueError(f"{venue} kapalı mum döndürmedi")
    if frame["timestamp"].duplicated().any():
        raise ValueError(f"{venue} duplicate mum")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if int(frame.iloc[0]["timestamp"]) != since_ms:
        raise ValueError(f"{venue} serisinin başlangıcı eksik")
    gap_report = hourly_gaps([int(value) for value in frame["timestamp"]])
    if int(frame.iloc[-1]["timestamp"]) + TIMEFRAME_MS != until_ms:
        raise ValueError(f"{venue} serisinin sonu eksik veya açık mum içeriyor")
    frame["date"] = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
    result = frame[["date", "open", "high", "low", "close", "volume"]]
    result.attrs["coverage"] = {
        "observed_hours": len(result),
        "missing_hours": sum(item["missing_hours"] for item in gap_report),
        "gaps": gap_report,
    }
    return result


def write_atomic(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name, suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        frame.to_feather(temp_path)
        temp_path.replace(destination)
    finally:
        temp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument(
        "--end",
        required=True,
        help="exclusive UTC boundary; Locked OOS için 2026-08-04T00:00:00Z",
    )
    args = parser.parse_args(argv)
    exchange = ccxt.coinbase({"enableRateLimit": True})
    frame = fetch_closed_candles(exchange, since_ms=_ms(args.start), until_ms=_ms(args.end))
    destination = market_data_root() / "coinbase" / "spot" / "BTC_USD-1h-spot.feather"
    write_atomic(frame, destination)
    coverage = frame.attrs["coverage"]
    print(
        f"OK: {destination} · {len(frame)} kapalı mum · "
        f"{coverage['missing_hours']} eksik saat/{len(coverage['gaps'])} gap"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
