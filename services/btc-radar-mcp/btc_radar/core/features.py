"""PIT-safe feature computation with an explicit minimum-history gate.

Why this module exists: a rolling percentile is only meaningful against a distribution that
actually exists.  Computing "funding is at its 97th percentile" from eleven samples is not a
measurement, it is a decoration.  Every feature here therefore returns either a value with
its evidence (sample count, span, largest gap, freshness) or an explicit unavailability
reason — never a quietly neutral number.

Determinism rules, on which bit-identical replay depends:
- Only PIT rows with ``available_at <= as_of`` are read (enforced by the store).
- The percentile is a midrank empirical CDF, not an interpolated quantile: ties are split
  in half, so the result never depends on sort stability or on floating-point interpolation.
- Every emitted float is rounded to the shared ``ROUND_NDIGITS`` precision.

Scope limit: these are FRAGILITY observations.  None of them claims a direction, and a
regime label is not derived here (SPEC §6 needs multi-layer coverage this service does not
have yet).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from btc_radar.core.snapshot import freshness
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import FeatureSpec

ROUND_NDIGITS = 6

REASON_NO_HISTORY = "no_history"
REASON_INSUFFICIENT_SAMPLES = "insufficient_samples"
REASON_INSUFFICIENT_SPAN = "insufficient_span"
REASON_HISTORY_GAP = "history_gap"
REASON_MISSING_CHANGE_WINDOW = "missing_change_window"
REASON_ZERO_BASE = "zero_change_base"
REASON_STALE = "stale"


@dataclass(frozen=True)
class FeatureResult:
    """One feature plus the evidence that it was allowed to be computed at all."""

    key: str
    metric: str
    kind: str
    available: bool
    value: float | None
    percentile: float | None
    sample_count: int
    span_seconds: float
    max_gap_seconds: float
    oldest_event_at: datetime | None
    newest_event_at: datetime | None
    quality: float
    freshness_factor: float
    unavailable_reason: str | None

    def as_breakdown(self) -> dict:
        """Compact, JSON-safe evidence block for the snapshot breakdown."""
        return {
            "feature": self.key,
            "metric": self.metric,
            "kind": self.kind,
            "value": self.value,
            "percentile": self.percentile,
            "sample_count": self.sample_count,
            "span_seconds": self.span_seconds,
            "max_gap_seconds": self.max_gap_seconds,
            "oldest_event_at": None
            if not self.oldest_event_at
            else self.oldest_event_at.isoformat(),
            "newest_event_at": None
            if not self.newest_event_at
            else self.newest_event_at.isoformat(),
            "quality": self.quality,
            "freshness": self.freshness_factor,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class _Sample:
    event_at: datetime
    value: float
    quality: float


def midrank_percentile(sample: Sequence[float], value: float) -> float:
    """Empirical CDF position of ``value`` in ``sample``, ties split in half.

    Deterministic by construction: no sorting, no interpolation, no tie-break ambiguity.
    """
    if not sample:
        raise ValueError("percentile için boş dağıtım kullanılamaz")
    below = sum(1 for item in sample if item < value)
    equal = sum(1 for item in sample if item == value)
    return round(100.0 * (below + 0.5 * equal) / len(sample), ROUND_NDIGITS)


def _parse_rows(rows: list[dict]) -> list[_Sample]:
    samples = [
        _Sample(
            event_at=datetime.fromisoformat(row["event_time"]).astimezone(UTC),
            value=float(row["raw_value"]),
            quality=float(row["quality"]),
        )
        for row in rows
    ]
    samples.sort(key=lambda item: item.event_at)
    return samples


def _max_gap_seconds(samples: Sequence[_Sample]) -> float:
    if len(samples) < 2:
        return 0.0
    gaps = [
        (samples[index + 1].event_at - samples[index].event_at).total_seconds()
        for index in range(len(samples) - 1)
    ]
    return round(max(gaps), ROUND_NDIGITS)


def _unavailable(
    key: str,
    spec: FeatureSpec,
    reason: str,
    *,
    samples: Sequence[_Sample] = (),
    sample_count: int | None = None,
) -> FeatureResult:
    return FeatureResult(
        key=key,
        metric=spec.metric,
        kind=spec.kind,
        available=False,
        value=None,
        percentile=None,
        sample_count=len(samples) if sample_count is None else sample_count,
        span_seconds=_span_seconds(samples),
        max_gap_seconds=_max_gap_seconds(samples),
        oldest_event_at=samples[0].event_at if samples else None,
        newest_event_at=samples[-1].event_at if samples else None,
        quality=min((item.quality for item in samples), default=0.0),
        freshness_factor=0.0,
        unavailable_reason=reason,
    )


def _span_seconds(samples: Sequence[_Sample]) -> float:
    if not samples:
        return 0.0
    return round((samples[-1].event_at - samples[0].event_at).total_seconds(), ROUND_NDIGITS)


def build_feature(
    key: str,
    spec: FeatureSpec,
    *,
    store: PointInTimeStore,
    as_of: datetime,
    asset: str,
    stale_multiple: float,
) -> FeatureResult:
    """Compute one feature from PIT history, or explain why it may not be computed."""
    if as_of.tzinfo is None:
        raise ValueError("as_of timezone-aware olmalı")
    as_of = as_of.astimezone(UTC)

    # A change feature needs one extra window of history to produce its oldest data point.
    warmup = timedelta(seconds=spec.change_window_seconds or 0.0)
    since = as_of - timedelta(days=spec.lookback_days) - warmup
    rows = store.read_series(metric=spec.metric, asset=asset, as_of=as_of, since=since)
    raw_samples = _parse_rows(rows)
    if not raw_samples:
        return _unavailable(key, spec, REASON_NO_HISTORY)

    max_gap = _max_gap_seconds(raw_samples)
    if max_gap > spec.max_gap_seconds:
        return _unavailable(key, spec, REASON_HISTORY_GAP, samples=raw_samples)

    if spec.kind == "abs_percentile":
        samples = raw_samples
        distribution_points = [(item.event_at, abs(item.value)) for item in samples]
        latest_value = samples[-1].value
    else:
        samples = raw_samples
        derived = _change_points(samples, window_seconds=float(spec.change_window_seconds or 0.0))
        if derived is None:
            return _unavailable(key, spec, REASON_ZERO_BASE, samples=raw_samples)
        distribution_points = [(event_at, abs(change)) for event_at, change in derived]
        if not distribution_points or distribution_points[-1][0] != samples[-1].event_at:
            return _unavailable(
                key,
                spec,
                REASON_MISSING_CHANGE_WINDOW,
                samples=raw_samples,
                sample_count=len(distribution_points),
            )
        latest_value = derived[-1][1]

    # The lookback window is measured on the feature's own points, not on the warmup rows.
    window_start = as_of - timedelta(days=spec.lookback_days)
    in_window = [point for point in distribution_points if point[0] >= window_start]
    evidence = [
        _Sample(event_at=event_at, value=value, quality=1.0) for event_at, value in in_window
    ]
    quality = min((item.quality for item in samples), default=0.0)

    if len(in_window) < spec.min_samples:
        return _unavailable(
            key, spec, REASON_INSUFFICIENT_SAMPLES, samples=evidence, sample_count=len(in_window)
        )
    span_seconds = _span_seconds(evidence)
    if span_seconds < spec.min_span_days * 86400.0:
        return _unavailable(
            key, spec, REASON_INSUFFICIENT_SPAN, samples=evidence, sample_count=len(in_window)
        )

    newest_event_at = evidence[-1].event_at
    freshness_factor = freshness(
        as_of=as_of,
        event_time=newest_event_at,
        expected_period_seconds=spec.expected_period_seconds,
        stale_multiple=stale_multiple,
    )
    if freshness_factor <= 0.0:
        return _unavailable(key, spec, REASON_STALE, samples=evidence, sample_count=len(in_window))

    percentile = midrank_percentile([item.value for item in evidence], abs(latest_value))
    return FeatureResult(
        key=key,
        metric=spec.metric,
        kind=spec.kind,
        available=True,
        value=round(latest_value, ROUND_NDIGITS),
        percentile=percentile,
        sample_count=len(in_window),
        span_seconds=span_seconds,
        max_gap_seconds=_max_gap_seconds(evidence),
        oldest_event_at=evidence[0].event_at,
        newest_event_at=newest_event_at,
        quality=round(quality, ROUND_NDIGITS),
        freshness_factor=freshness_factor,
        unavailable_reason=None,
    )


def _change_points(
    samples: Sequence[_Sample], *, window_seconds: float
) -> list[tuple[datetime, float]] | None:
    """Relative change over an exact window; a point without its counterpart is dropped.

    An exact timestamp match is intentional.  Tolerating "close enough" partners would make
    the change silently depend on sampling jitter, and a missing bucket is information: it
    means we do not know that change, not that the change was zero.
    """
    by_event = {item.event_at: item.value for item in samples}
    window = timedelta(seconds=window_seconds)
    points: list[tuple[datetime, float]] = []
    for item in samples:
        base = by_event.get(item.event_at - window)
        if base is None:
            continue
        if base == 0.0:
            return None
        points.append((item.event_at, round((item.value - base) / base, ROUND_NDIGITS)))
    return points
