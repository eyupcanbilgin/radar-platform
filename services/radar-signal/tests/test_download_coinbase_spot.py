"""Public Coinbase spot OHLCV downloader acceptance tests (fully synthetic)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from download_coinbase_spot import (  # noqa: E402
    TIMEFRAME_MS,
    _ms,
    fetch_closed_candles,
    write_atomic,
)


def _row(timestamp: int) -> list[float]:
    return [timestamp, 100.0, 102.0, 99.0, 101.0, 10.0]


class FakeExchange:
    def __init__(self, rows: list[list[float]], *, repeat_first_page: bool = False):
        self.rows = rows
        self.repeat_first_page = repeat_first_page
        self.calls: list[tuple[str, str, int, int]] = []

    def fetch_ohlcv(self, symbol, timeframe, *, since, limit):
        self.calls.append((symbol, timeframe, since, limit))
        if self.repeat_first_page:
            return self.rows[:limit]
        return [row for row in self.rows if row[0] >= since][:limit]


def test_fetches_exact_closed_range_across_pages():
    # The last row starts exactly at the exclusive boundary and is still open there.
    rows = [_row(hour * TIMEFRAME_MS) for hour in range(303)]
    exchange = FakeExchange(rows)

    frame = fetch_closed_candles(exchange, since_ms=0, until_ms=302 * TIMEFRAME_MS)

    assert len(frame) == 302
    assert frame.iloc[0]["date"] == pd.Timestamp(0, unit="ms", tz="UTC")
    assert frame.iloc[-1]["date"] == pd.Timestamp(301 * TIMEFRAME_MS, unit="ms", tz="UTC")
    assert len(exchange.calls) == 2
    assert all(call[:2] == ("BTC/USD", "1h") for call in exchange.calls)


@pytest.mark.parametrize(
    ("rows", "until_ms", "message"),
    [
        ([_row(0), _row(0)], 2 * TIMEFRAME_MS, "duplicate"),
        ([_row(TIMEFRAME_MS)], 2 * TIMEFRAME_MS, "başlangıcı eksik"),
        ([_row(0)], 2 * TIMEFRAME_MS, "sonu eksik"),
    ],
)
def test_rejects_incomplete_or_ambiguous_history(rows, until_ms, message):
    with pytest.raises(ValueError, match=message):
        fetch_closed_candles(FakeExchange(rows), since_ms=0, until_ms=until_ms)


def test_rejects_non_progressing_pagination():
    rows = [_row(hour * TIMEFRAME_MS) for hour in range(300)]
    with pytest.raises(ValueError, match="pagination ilerlemedi"):
        fetch_closed_candles(
            FakeExchange(rows, repeat_first_page=True),
            since_ms=0,
            until_ms=301 * TIMEFRAME_MS,
        )


def test_preserves_but_explicitly_reports_internal_exchange_gaps():
    frame = fetch_closed_candles(
        FakeExchange([_row(0), _row(2 * TIMEFRAME_MS)]),
        since_ms=0,
        until_ms=3 * TIMEFRAME_MS,
    )

    assert len(frame) == 2
    assert frame.attrs["coverage"]["missing_hours"] == 1
    assert len(frame.attrs["coverage"]["gaps"]) == 1


def test_atomic_write_is_readable_and_idempotent(tmp_path):
    destination = tmp_path / "coinbase" / "spot.feather"
    frame = pd.DataFrame(
        {
            "date": [datetime(2026, 8, 1, tzinfo=UTC)],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [3.0],
        }
    )

    write_atomic(frame, destination)
    write_atomic(frame, destination)

    pd.testing.assert_frame_equal(pd.read_feather(destination), frame)
    assert not list(destination.parent.glob("*.tmp"))


def test_ms_requires_timezone_and_normalizes_to_utc():
    assert _ms("1970-01-01T03:00:00+03:00") == 0
    with pytest.raises(ValueError, match="timezone-aware"):
        _ms("2026-08-04T00:00:00")
