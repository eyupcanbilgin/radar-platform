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
    history_mode: str
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
    complete: bool
    gap_ok: bool
    fresh: bool
    healthy: bool

    @property
    def meets_expectation(self) -> bool:
        """Bu metrikten beklenebilecek en iyi durumda mı — geçmişi doldurulabilir mi bilerek.

        ``live_only`` bir metriğin toplama başlamadan önceki ve kesinti sırasındaki
        boşlukları **yapısal olarak onarılamaz**: uçta geçmiş yoktur, backfill mümkün
        değildir.  Onları genel sağlık bayrağına katmak, bayrağı aylarca `False` tutar ve
        her zaman `False` olan bir sağlık göstergesi hiçbir şeyi korumaz — operatöre onu
        görmezden gelmeyi öğretir.

        ``live_only`` için ölçülebilir tek soru şudur: **hâlâ topluyor mu?**  Bu yüzden
        beklenti tazeliktir.  ``backfill_and_live`` metrikte ise boşluk gerçek bir kusurdur
        ve tam sağlık aranır.

        Ayrıntı gizlenmez: ``complete``, ``gap_ok`` ve ``healthy`` alanları raporda aynen
        durur; değişen yalnız **genel bayrağın neye bakacağıdır**.
        """
        if self.history_mode == "live_only":
            return self.fresh
        return self.healthy

    def as_payload(self) -> dict:
        return {**asdict(self), "meets_expectation": self.meets_expectation}


def metric_coverage(
    store: PointInTimeStore,
    *,
    metric: str,
    asset: str,
    as_of: datetime,
    window_seconds: float,
    expected_period_seconds: float,
    tolerated_gap_seconds: float,
    history_mode: str = "unspecified",
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
    complete = observed >= expected_samples

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
        history_mode=history_mode,
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
        complete=complete,
        gap_ok=gap_ok,
        fresh=fresh,
        healthy=complete and gap_ok and fresh,
    )


def collection_coverage(
    store: PointInTimeStore,
    *,
    rules: SignalRulesConfig,
    as_of: datetime,
    window_seconds: float,
    asset: str = "BTC",
) -> list[MetricCoverage]:
    """Coverage for scoring inputs and explicitly monitored non-scoring collectors."""
    specs = {
        spec.metric: (
            spec.expected_period_seconds,
            spec.max_gap_seconds,
            "backfill_and_live",
        )
        for spec in rules.features.values()
    }
    for metric, spec in rules.collection_metrics.items():
        candidate = (spec.expected_period_seconds, spec.max_gap_seconds, spec.history_mode)
        existing = specs.get(metric)
        if existing is not None and existing[:2] != candidate[:2]:
            raise ValueError(
                f"{metric} feature ve collection cadence tanimlari birbiriyle celisiyor"
            )
        specs[metric] = candidate
    return [
        metric_coverage(
            store,
            metric=metric,
            asset=asset,
            as_of=as_of,
            window_seconds=window_seconds,
            expected_period_seconds=spec[0],
            tolerated_gap_seconds=spec[1],
            history_mode=spec[2],
        )
        for metric, spec in sorted(specs.items())
    ]
