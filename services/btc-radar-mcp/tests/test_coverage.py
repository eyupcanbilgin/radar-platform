"""Coverage: the data itself must show whether collection was uninterrupted."""

from datetime import UTC, datetime, timedelta

from btc_radar.core.config import load_signal_rules
from btc_radar.core.coverage import collection_coverage, metric_coverage
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.observation import RawObservation

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
METRIC = "open_interest_1h"
WINDOW = 2 * 86400.0
PERIOD = 3600.0
TOLERANCE = 10800.0


def _observation(event_at: datetime, *, available_at: datetime | None = None) -> RawObservation:
    return RawObservation(
        timestamp_utc=event_at,
        retrieved_at_utc=event_at + timedelta(seconds=60),
        available_at_utc=available_at or event_at + timedelta(seconds=60),
        asset="BTC",
        venue="binance_futures",
        metric=METRIC,
        raw_value=100_000.0,
        unit="BTC",
        window="1h",
        source_group="derivatives",
        source_url="https://fapi.binance.com/futures/data/openInterestHist",
        quality=1.0,
    )


def _hourly(store: PointInTimeStore, hours: range) -> None:
    store.append(
        [_observation(NOW - timedelta(hours=offset)) for offset in hours],
        provider="binance_futures_history",
    )


def _coverage(store: PointInTimeStore, *, as_of: datetime = NOW):
    return metric_coverage(
        store,
        metric=METRIC,
        asset="BTC",
        as_of=as_of,
        window_seconds=WINDOW,
        expected_period_seconds=PERIOD,
        tolerated_gap_seconds=TOLERANCE,
    )


def test_a_complete_series_reports_full_coverage():
    with PointInTimeStore() as store:
        _hourly(store, range(1, 49))
        report = _coverage(store)

    assert report.expected_samples == 48
    assert report.observed_samples == 48
    assert report.coverage_ratio == 1.0
    assert report.max_gap_seconds == 3600.0
    assert report.gap_ok is True
    assert report.fresh is True
    assert report.healthy is True


def test_an_outage_is_located_not_just_counted():
    with PointInTimeStore() as store:
        _hourly(store, range(1, 20))
        _hourly(store, range(26, 49))  # NOW-26h ile NOW-19h arasında kesinti
        report = _coverage(store)

    assert report.observed_samples == 42
    assert report.coverage_ratio < 1.0
    assert report.max_gap_seconds == 7 * 3600.0
    assert report.longest_gap_start_at.startswith("2026-08-03T10:00")
    assert report.longest_gap_end_at.startswith("2026-08-03T17:00")
    # 7 saat, 3 saatlik toleransın üstünde: seri "tam" sayılmaz.
    assert report.gap_ok is False
    assert report.healthy is False


def test_a_stopped_collector_shows_up_as_stale_even_with_a_dense_history():
    with PointInTimeStore() as store:
        _hourly(store, range(8, 49))  # son 7 saat hiç toplanmamış
        report = _coverage(store)

    assert report.gap_ok is True  # geçmişte delik yok
    assert report.fresh is False  # ama toplama durmuş
    assert report.healthy is False
    assert report.seconds_since_newest == 8 * 3600.0


def test_an_empty_store_is_reported_as_unhealthy_not_as_perfect():
    with PointInTimeStore() as store:
        report = _coverage(store)

    assert report.observed_samples == 0
    assert report.coverage_ratio == 0.0
    assert report.newest_event_at is None
    assert report.seconds_since_newest is None
    assert report.healthy is False


def test_coverage_respects_the_point_in_time_cutoff():
    with PointInTimeStore() as store:
        _hourly(store, range(1, 49))
        # Yayın anı gelecekte olan satır, geçmiş bir kapsama raporunda görünmemeli.
        store.append(
            [_observation(NOW, available_at=NOW + timedelta(hours=2))],
            provider="binance_futures_history",
        )
        report = _coverage(store)

    assert report.newest_event_at.startswith("2026-08-04T11:00")


def test_collection_coverage_uses_the_shipped_feature_specs():
    with PointInTimeStore() as store:
        _hourly(store, range(1, 49))
        reports = collection_coverage(
            store, rules=load_signal_rules(), as_of=NOW, window_seconds=WINDOW
        )

    metrics = {report.metric: report for report in reports}
    # Config'de tanımlı her feature metriği raporlanır; toplanmamış olan da görünür.
    assert set(metrics) == {"funding_rate_settled", "open_interest_value_1h"}
    assert metrics["funding_rate_settled"].observed_samples == 0
    assert metrics["funding_rate_settled"].expected_period_seconds == 28800.0
    assert metrics["funding_rate_settled"].tolerated_gap_seconds == 43200.0
