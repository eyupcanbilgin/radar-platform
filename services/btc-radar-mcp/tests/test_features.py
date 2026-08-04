"""Feature layer: minimum-history gate, PIT safety and deterministic percentiles."""

from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.features import (
    REASON_HISTORY_GAP,
    REASON_INSUFFICIENT_SAMPLES,
    REASON_INSUFFICIENT_SPAN,
    REASON_MISSING_CHANGE_WINDOW,
    REASON_NO_HISTORY,
    REASON_STALE,
    build_feature,
    midrank_percentile,
)
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import FeatureSpec
from btc_radar.models.observation import RawObservation

AS_OF = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
STALE_MULTIPLE = 3.0

ABS_SPEC = FeatureSpec(
    kind="abs_percentile",
    metric="funding_rate_settled",
    lookback_days=10.0,
    expected_period_seconds=28800.0,
    min_samples=5,
    min_span_days=2.0,
    max_gap_seconds=43200.0,
)

CHANGE_SPEC = FeatureSpec(
    kind="change_abs_percentile",
    metric="open_interest_value_1h",
    change_window_seconds=7200.0,
    lookback_days=1.0,
    expected_period_seconds=3600.0,
    min_samples=4,
    min_span_days=0.0,
    max_gap_seconds=7200.0,
)


def _observation(
    *, metric: str, event_at: datetime, value: float, available_at: datetime | None = None
) -> RawObservation:
    return RawObservation(
        timestamp_utc=event_at,
        retrieved_at_utc=event_at + timedelta(seconds=60),
        available_at_utc=available_at or event_at + timedelta(seconds=60),
        asset="BTC",
        venue="binance_futures",
        metric=metric,
        raw_value=value,
        unit="ratio",
        source_group="derivatives",
        source_url="https://fapi.binance.com/fapi/v1/fundingRate",
        quality=1.0,
    )


def _seed(store: PointInTimeStore, observations: list[RawObservation]) -> None:
    store.append(observations, provider="binance_futures_history")


def _funding_series(count: int, *, step_hours: int = 8, values: list[float] | None = None):
    """``count`` settlements ending one step before ``AS_OF``."""
    series = []
    for index in range(count):
        event_at = AS_OF - timedelta(hours=step_hours * (count - index))
        value = values[index] if values else 0.00001 * (index % 7)
        series.append(_observation(metric=ABS_SPEC.metric, event_at=event_at, value=value))
    return series


def _build(spec: FeatureSpec, store: PointInTimeStore, *, as_of: datetime = AS_OF):
    return build_feature(
        "test_feature", spec, store=store, as_of=as_of, asset="BTC", stale_multiple=STALE_MULTIPLE
    )


def test_midrank_percentile_splits_ties_and_rejects_empty_distribution():
    assert midrank_percentile([1.0, 2.0, 3.0, 4.0], 4.0) == 87.5
    assert midrank_percentile([1.0, 1.0, 1.0, 1.0], 1.0) == 50.0
    assert midrank_percentile([5.0, 6.0], 1.0) == 0.0
    with pytest.raises(ValueError, match="boş dağıtım"):
        midrank_percentile([], 1.0)


def test_abs_percentile_uses_magnitude_so_crowded_shorts_also_register():
    with PointInTimeStore() as store:
        values = [0.0001] * 9 + [-0.0009]
        _seed(store, _funding_series(10, values=values))
        feature = _build(ABS_SPEC, store)

    assert feature.available is True
    assert feature.value == pytest.approx(-0.0009)
    # Negatif ama en uç değer: mutlak konum tepe yüzdelikte olmalı.
    assert feature.percentile == 95.0
    assert feature.sample_count == 10
    assert feature.freshness_factor == 1.0


def test_empty_history_is_unavailable_not_neutral():
    with PointInTimeStore() as store:
        feature = _build(ABS_SPEC, store)
    assert feature.available is False
    assert feature.unavailable_reason == REASON_NO_HISTORY
    assert feature.value is None and feature.percentile is None


def test_too_few_samples_blocks_the_feature():
    with PointInTimeStore() as store:
        _seed(store, _funding_series(4))
        feature = _build(ABS_SPEC, store)
    assert feature.available is False
    assert feature.unavailable_reason == REASON_INSUFFICIENT_SAMPLES
    assert feature.sample_count == 4


def test_enough_samples_but_too_short_a_span_still_blocks():
    spec = ABS_SPEC.model_copy(update={"min_span_days": 9.0})
    with PointInTimeStore() as store:
        _seed(store, _funding_series(6))
        feature = _build(spec, store)
    assert feature.available is False
    assert feature.unavailable_reason == REASON_INSUFFICIENT_SPAN


def test_a_collector_outage_shows_up_as_a_history_gap():
    with PointInTimeStore() as store:
        series = _funding_series(10)
        # 8 saatlik ritimde 24 saatlik bir delik: toplayıcı durmuş demektir.
        _seed(store, series[:4] + series[7:])
        feature = _build(ABS_SPEC, store)
    assert feature.available is False
    assert feature.unavailable_reason == REASON_HISTORY_GAP
    assert feature.max_gap_seconds == 115200.0  # 4 adımlık kayıp = 32 saat


def test_stale_history_blocks_even_when_samples_are_plentiful():
    with PointInTimeStore() as store:
        _seed(store, _funding_series(12))
        # 8h periyot × stale_multiple 3 → 24 saatten yaşlı seri f=0 üretir.
        feature = _build(ABS_SPEC, store, as_of=AS_OF + timedelta(hours=30))
    assert feature.available is False
    assert feature.unavailable_reason == REASON_STALE


def test_rows_published_after_as_of_cannot_enter_the_feature():
    with PointInTimeStore() as store:
        _seed(store, _funding_series(10, values=[0.0001] * 9 + [-0.0009]))
        # Sonradan yayınlanan bir uç değer geçmiş kararı değiştiremez.
        _seed(
            store,
            [
                _observation(
                    metric=ABS_SPEC.metric,
                    event_at=AS_OF - timedelta(hours=1),
                    value=0.05,
                    available_at=AS_OF + timedelta(minutes=5),
                )
            ],
        )
        at_cutoff = _build(ABS_SPEC, store)
        later = _build(ABS_SPEC, store, as_of=AS_OF + timedelta(minutes=10))

    assert at_cutoff.sample_count == 10
    assert at_cutoff.value == pytest.approx(-0.0009)
    assert later.value == pytest.approx(0.05)


def test_feature_computation_is_deterministic():
    with PointInTimeStore() as store:
        _seed(store, _funding_series(10))
        assert _build(ABS_SPEC, store) == _build(ABS_SPEC, store)


def _hourly_notional(count: int, *, start_gap_hours: int = 1):
    series = []
    for index in range(count):
        event_at = AS_OF - timedelta(hours=count - index + start_gap_hours - 1)
        # Sabit taban: her 2 saatlik değişim sıfırdır, tek sapma testin kendi eklediğidir.
        value = 7_000_000_000.0
        series.append(_observation(metric=CHANGE_SPEC.metric, event_at=event_at, value=value))
    return series


def test_change_feature_measures_relative_change_over_an_exact_window():
    with PointInTimeStore() as store:
        series = _hourly_notional(12)
        series[-1] = _observation(
            metric=CHANGE_SPEC.metric,
            event_at=series[-1].timestamp_utc,
            value=7_700_000_000.0,
        )
        _seed(store, series)
        feature = _build(CHANGE_SPEC, store)

    assert feature.available is True
    # 2 saat önceki 7.0e9 tabanına göre %10 artış.
    assert feature.value == pytest.approx(0.1)
    assert feature.sample_count == 10  # 12 saatlik seride 2 saatlik pencereyle 10 değişim
    assert feature.percentile == 95.0


def test_change_feature_without_its_counterpart_bucket_is_unavailable():
    with PointInTimeStore() as store:
        series = _hourly_notional(12)
        # En yeni noktanın 2 saat önceki eşi eksik → o değişim BİLİNMİYOR, sıfır değil.
        del series[-3]
        _seed(store, series)
        feature = _build(CHANGE_SPEC, store)

    assert feature.available is False
    assert feature.unavailable_reason == REASON_MISSING_CHANGE_WINDOW
