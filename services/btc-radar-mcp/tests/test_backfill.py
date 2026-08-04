"""Backfill paging: forward for funding, backward for OI, always bounded and honest."""

from datetime import UTC, datetime, timedelta

from btc_radar.core.backfill import backfill_funding, backfill_open_interest, backfill_spot_ohlcv
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.observation import RawObservation
from btc_radar.providers.binance_futures_history import (
    FUNDING_SETTLED_METRIC,
    OPEN_INTEREST_HOURLY_METRIC,
    HistoryWindowError,
)
from btc_radar.providers.binance_spot import OHLCV_METRIC

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
LAG = timedelta(seconds=60)


def _observation(metric: str, event_at: datetime, value: float) -> RawObservation:
    return RawObservation(
        timestamp_utc=event_at,
        retrieved_at_utc=NOW,
        available_at_utc=event_at + LAG,
        asset="BTC",
        venue="binance_futures",
        metric=metric,
        raw_value=value,
        unit="ratio",
        source_group="derivatives",
        source_url="https://fapi.binance.com/test",
        quality=1.0,
    )


class FakeHistoryProvider:
    """A deterministic stand-in with the two real paging behaviours."""

    name = "binance_futures_history"

    def __init__(self, *, step: timedelta, oldest: datetime, retention: datetime | None = None):
        self.step = step
        self.oldest = oldest
        self.retention = retention
        self.calls: list[dict] = []

    def _grid(self, start: datetime, end: datetime) -> list[datetime]:
        points, cursor = [], self.oldest
        while cursor <= end:
            if cursor >= start:
                points.append(cursor)
            cursor += self.step
        return points

    async def fetch(self, metric: str, **params):
        self.calls.append({"metric": metric, **params})
        limit = params["limit"]
        if metric == FUNDING_SETTLED_METRIC:
            start = params.get("start_time", self.oldest)
            end = params.get("end_time", NOW)
            window = self._grid(start, end)[:limit]  # forward page
        else:
            end = params["end_time"]
            if self.retention and end < self.retention:
                raise HistoryWindowError("saklama penceresi disinda")
            window = self._grid(self.oldest, end)[-limit:]  # backward tail page
        return [_observation(metric, event_at, 1.0) for event_at in window]


class FakeSpotHistoryProvider:
    name = "binance_spot_history"

    def __init__(self, *, oldest: datetime):
        self.oldest = oldest
        self.calls: list[dict] = []

    async def fetch(self, metric: str, **params):
        self.calls.append({"metric": metric, **params})
        cursor = self.oldest
        events: list[datetime] = []
        while cursor < params["end_time"]:
            if cursor >= params["start_time"]:
                events.append(cursor)
            cursor += timedelta(hours=1)
        events = events[: params["limit"]]
        observations: list[RawObservation] = []
        for event_at in events:
            for field in ("open", "high", "low", "close", "volume"):
                observations.append(_observation(f"spot_{field}", event_at, 1.0))
        return observations


async def test_funding_pages_forward_until_the_window_is_covered():
    provider = FakeHistoryProvider(step=timedelta(hours=8), oldest=NOW - timedelta(days=10))
    with PointInTimeStore() as store:
        result = await backfill_funding(
            provider, store, start=NOW - timedelta(days=10), end=NOW, page_limit=5
        )

    assert result.metric == FUNDING_SETTLED_METRIC
    assert result.pages > 1
    assert result.inserted == result.fetched == 31
    assert result.oldest_event_at == NOW - timedelta(days=10)
    assert result.max_gap_seconds == 28800.0
    assert result.truncated_reason is None
    # Her sayfa bir öncekinin son olayından sonra başlamalı; aynı sayfa iki kez istenmez.
    starts = [call["start_time"] for call in provider.calls]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)


async def test_open_interest_pages_backward_and_stops_at_the_requested_start():
    provider = FakeHistoryProvider(step=timedelta(hours=1), oldest=NOW - timedelta(days=3))
    with PointInTimeStore() as store:
        result = await backfill_open_interest(
            provider, store, start=NOW - timedelta(days=1), end=NOW, page_limit=10
        )

    ends = [call["end_time"] for call in provider.calls]
    assert result.metric == OPEN_INTEREST_HOURLY_METRIC
    assert ends == sorted(ends, reverse=True)  # geriye doğru sayfalama
    assert result.oldest_event_at <= NOW - timedelta(days=1)
    assert result.max_gap_seconds == 3600.0
    assert result.truncated_reason is None


async def test_exchange_retention_truncates_without_losing_what_was_stored():
    provider = FakeHistoryProvider(
        step=timedelta(hours=1),
        oldest=NOW - timedelta(days=60),
        retention=NOW - timedelta(days=2),
    )
    with PointInTimeStore() as store:
        result = await backfill_open_interest(
            provider, store, start=NOW - timedelta(days=45), end=NOW, page_limit=24
        )
        stored = store.count()

    assert result.truncated_reason == "exchange_retention"
    assert result.inserted > 0
    assert stored == result.inserted
    # Saklama sınırının ötesi yalnız kendi deposundan gelebilir; sessizce "veri yok" demeyiz.
    assert result.oldest_event_at > NOW - timedelta(days=45)


async def test_page_budget_is_reported_instead_of_looping_forever():
    provider = FakeHistoryProvider(step=timedelta(hours=1), oldest=NOW - timedelta(days=365))
    with PointInTimeStore() as store:
        result = await backfill_open_interest(
            provider, store, start=NOW - timedelta(days=365), end=NOW, page_limit=10, max_pages=3
        )

    assert result.pages == 3
    assert result.truncated_reason == "max_pages"


async def test_repeated_backfill_is_idempotent_in_the_store():
    provider = FakeHistoryProvider(step=timedelta(hours=8), oldest=NOW - timedelta(days=5))
    with PointInTimeStore() as store:
        first = await backfill_funding(
            provider, store, start=NOW - timedelta(days=5), end=NOW, page_limit=100
        )
        second = await backfill_funding(
            provider, store, start=NOW - timedelta(days=5), end=NOW, page_limit=100
        )
        stored = store.count()

    assert first.inserted > 0
    assert second.inserted == 0  # aynı bilgi-zamanı satırı iki kez yazılmaz
    assert stored == first.inserted


async def test_spot_ohlcv_pages_forward_and_counts_candles_as_events():
    provider = FakeSpotHistoryProvider(oldest=NOW - timedelta(days=3))
    with PointInTimeStore() as store:
        result = await backfill_spot_ohlcv(
            provider,
            store,
            start=NOW - timedelta(days=2),
            end=NOW,
            page_limit=10,
        )

    assert result.metric == OHLCV_METRIC
    assert result.pages == 5
    assert result.fetched == result.inserted == 48 * 5
    assert result.oldest_event_at == NOW - timedelta(days=2)
    assert result.newest_event_at == NOW - timedelta(hours=1)
    assert result.max_gap_seconds == 3600.0
    starts = [call["start_time"] for call in provider.calls]
    assert starts == sorted(starts)


async def test_repeated_spot_backfill_is_idempotent_in_the_store():
    provider = FakeSpotHistoryProvider(oldest=NOW - timedelta(days=1))
    with PointInTimeStore() as store:
        first = await backfill_spot_ohlcv(
            provider,
            store,
            start=NOW - timedelta(days=1),
            end=NOW,
            page_limit=100,
        )
        second = await backfill_spot_ohlcv(
            provider,
            store,
            start=NOW - timedelta(days=1),
            end=NOW,
            page_limit=100,
        )

        assert first.inserted == 24 * 5
        assert second.inserted == 0
        assert store.count() == first.inserted
