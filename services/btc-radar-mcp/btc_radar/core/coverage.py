"""Data-derived proof of uninterrupted collection.

The heartbeat log proves the process ran.  It cannot prove the series is complete: a run that
"succeeded" while the endpoint quietly returned a shorter page still leaves a hole.  This
module answers the harder question by measuring the collected series itself — how many
samples exist against how many the sampling period implies, and where the longest hole is.

Thresholds are not invented here.  The expected period and the tolerated gap come from the
same ``signal_rules.yaml`` feature specs that gate the features, so an operator report and a
feature blocker can never disagree about what "a gap" means.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import SignalRulesConfig

ROUND_NDIGITS = 6


@dataclass(frozen=True)
class MetricCoverage:
    """One metric's collection health over a window ending at ``as_of``."""

    metric: str
    window_seconds: float
    expected_period_seconds: float
    expected_samples: int
    observed_samples: int
    coverage_ratio: float
    max_gap_seconds: float
    tolerated_gap_seconds: float
    longest_gap_start_at: str | None
    longest_gap_end_at: str | None
    oldest_event_at: str | None
    newest_event_at: str | None
    seconds_since_newest: float | None
    gap_ok: bool
    fresh: bool
    healthy: bool

    def as_payload(self) -> dict:
        return asdict(self)


def metric_coverage(
    store: PointInTimeStore,
    *,
    metric: str,
    asset: str,
    as_of: datetime,
    window_seconds: float,
    expected_period_seconds: float,
    tolerated_gap_seconds: float,
) -> MetricCoverage:
    """Measure one metric's completeness using only rows knowable at ``as_of``."""
    if expected_period_seconds <= 0:
        raise ValueError("expected_period_seconds > 0 olmalı")
    if window_seconds <= 0:
        raise ValueError("window_seconds > 0 olmalı")

    as_of = as_of.astimezone(UTC)
    since = as_of - timedelta(seconds=window_seconds)
    rows = store.read_series(metric=metric, asset=asset, as_of=as_of, since=since)
    events = [datetime.fromisoformat(row["event_time"]).astimezone(UTC) for row in rows]

    expected_samples = int(window_seconds // expected_period_seconds)
    observed = len(events)
    ratio = round(observed / expected_samples, ROUND_NDIGITS) if expected_samples else 0.0

    longest_gap = 0.0
    gap_start: datetime | None = None
    gap_end: datetime | None = None
    for index in range(len(events) - 1):
        gap = (events[index + 1] - events[index]).total_seconds()
        if gap > longest_gap:
            longest_gap, gap_start, gap_end = gap, events[index], events[index + 1]

    newest = events[-1] if events else None
    age = None if newest is None else round((as_of - newest).total_seconds(), ROUND_NDIGITS)
    # Bir periyot yaşındaki veri normaldir; tolerans boşluk toleransıyla aynı ölçüdedir ki
    # rapor ile feature kapısı aynı şeye "boşluk" desin.
    fresh = age is not None and age <= tolerated_gap_seconds
    gap_ok = bool(events) and longest_gap <= tolerated_gap_seconds

    return MetricCoverage(
        metric=metric,
        window_seconds=float(window_seconds),
        expected_period_seconds=float(expected_period_seconds),
        expected_samples=expected_samples,
        observed_samples=observed,
        coverage_ratio=ratio,
        max_gap_seconds=round(longest_gap, ROUND_NDIGITS),
        tolerated_gap_seconds=float(tolerated_gap_seconds),
        longest_gap_start_at=None if gap_start is None else gap_start.isoformat(),
        longest_gap_end_at=None if gap_end is None else gap_end.isoformat(),
        oldest_event_at=None if not events else events[0].isoformat(),
        newest_event_at=None if newest is None else newest.isoformat(),
        seconds_since_newest=age,
        gap_ok=gap_ok,
        fresh=fresh,
        healthy=gap_ok and fresh,
    )


def collection_coverage(
    store: PointInTimeStore,
    *,
    rules: SignalRulesConfig,
    as_of: datetime,
    window_seconds: float,
    asset: str = "BTC",
) -> list[MetricCoverage]:
    """Coverage for every metric the configured features depend on, in metric order."""
    specs = {spec.metric: spec for spec in rules.features.values()}
    return [
        metric_coverage(
            store,
            metric=metric,
            asset=asset,
            as_of=as_of,
            window_seconds=window_seconds,
            expected_period_seconds=spec.expected_period_seconds,
            tolerated_gap_seconds=spec.max_gap_seconds,
        )
        for metric, spec in sorted(specs.items())
    ]
