"""Paged history backfill into the PIT store.

The two endpoints page in opposite directions and this module encodes that difference once
(see ``providers/binance_futures_history`` for the probe results behind it):

- settled funding pages FORWARD from ``start_time``;
- hourly open interest pages BACKWARD from ``end_time``, because supplying ``start_time``
  alone returns the newest rows instead of the oldest.

Every loop is bounded by ``max_pages``.  An unbounded "just keep asking" loop against a
rate-limited public endpoint is how an IP gets banned, and a silent partial result is worse
than a loud stop: the caller is told how much history was actually stored.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from btc_radar.core.store import PointInTimeStore
from btc_radar.models.observation import RawObservation
from btc_radar.providers.binance_futures_history import (
    FUNDING_SETTLED_METRIC,
    OPEN_INTEREST_HOURLY_METRIC,
    BinanceFuturesHistoryProvider,
    HistoryWindowError,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 40


@dataclass(frozen=True)
class BackfillResult:
    """What was actually stored — never a claim about what was requested."""

    metric: str
    pages: int
    fetched: int
    inserted: int
    oldest_event_at: datetime | None
    newest_event_at: datetime | None
    max_gap_seconds: float
    truncated_reason: str | None

    def as_payload(self) -> dict:
        return {
            "metric": self.metric,
            "pages": self.pages,
            "fetched": self.fetched,
            "inserted": self.inserted,
            "oldest_event_at": None
            if not self.oldest_event_at
            else self.oldest_event_at.isoformat(),
            "newest_event_at": None
            if not self.newest_event_at
            else self.newest_event_at.isoformat(),
            "max_gap_seconds": self.max_gap_seconds,
            "truncated_reason": self.truncated_reason,
        }


def _event_times(observations: list[RawObservation]) -> list[datetime]:
    return sorted({observation.timestamp_utc for observation in observations})


def _summarize(
    metric: str,
    *,
    pages: int,
    fetched: int,
    inserted: int,
    events: set[datetime],
    truncated_reason: str | None,
) -> BackfillResult:
    ordered = sorted(events)
    gaps = [
        (ordered[index + 1] - ordered[index]).total_seconds() for index in range(len(ordered) - 1)
    ]
    return BackfillResult(
        metric=metric,
        pages=pages,
        fetched=fetched,
        inserted=inserted,
        oldest_event_at=ordered[0] if ordered else None,
        newest_event_at=ordered[-1] if ordered else None,
        max_gap_seconds=max(gaps) if gaps else 0.0,
        truncated_reason=truncated_reason,
    )


async def backfill_funding(
    provider: BinanceFuturesHistoryProvider,
    store: PointInTimeStore,
    *,
    start: datetime,
    end: datetime,
    page_limit: int = 1000,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> BackfillResult:
    """Walk settled funding forward from ``start`` until ``end`` or the page budget."""
    cursor = start.astimezone(UTC)
    end = end.astimezone(UTC)
    pages = fetched = inserted = 0
    events: set[datetime] = set()
    truncated: str | None = None

    while pages < max_pages:
        page = await provider.fetch(
            FUNDING_SETTLED_METRIC, start_time=cursor, end_time=end, limit=page_limit
        )
        pages += 1
        if not page:
            break
        fetched += len(page)
        inserted += store.append(page, provider=provider.name)
        page_events = _event_times(page)
        events.update(page_events)
        if len(page_events) < page_limit:
            break
        cursor = page_events[-1] + timedelta(milliseconds=1)
        if cursor >= end:
            break
    else:
        truncated = "max_pages"

    return _summarize(
        FUNDING_SETTLED_METRIC,
        pages=pages,
        fetched=fetched,
        inserted=inserted,
        events=events,
        truncated_reason=truncated,
    )


async def backfill_open_interest(
    provider: BinanceFuturesHistoryProvider,
    store: PointInTimeStore,
    *,
    start: datetime,
    end: datetime,
    page_limit: int = 500,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> BackfillResult:
    """Walk hourly open interest backward from ``end`` down to ``start``.

    A ``HistoryWindowError`` is a normal outcome, not a crash: it simply means the exchange
    no longer retains that far back.  Whatever was already stored is kept and reported.
    """
    cursor = end.astimezone(UTC)
    start = start.astimezone(UTC)
    pages = fetched = inserted = 0
    events: set[datetime] = set()
    truncated: str | None = None

    while pages < max_pages:
        try:
            page = await provider.fetch(
                OPEN_INTEREST_HOURLY_METRIC, end_time=cursor, limit=page_limit
            )
        except HistoryWindowError:
            truncated = "exchange_retention"
            break
        pages += 1
        if not page:
            truncated = truncated or "empty_page"
            break
        fetched += len(page)
        inserted += store.append(page, provider=provider.name)
        page_events = _event_times(page)
        events.update(page_events)
        oldest = page_events[0]
        if oldest <= start:
            break
        cursor = oldest - timedelta(milliseconds=1)
    else:
        truncated = "max_pages"

    return _summarize(
        OPEN_INTEREST_HOURLY_METRIC,
        pages=pages,
        fetched=fetched,
        inserted=inserted,
        events=events,
        truncated_reason=truncated,
    )
