"""Fully synthetic tests: a health flag that can never be true protects nothing.

`spot_perp_basis` and `order_book_spread_bps` are `live_only` — the exchange serves no
history for them, so gaps from before collection started (or from a past outage) can never
be repaired.  Counting those gaps in the overall health flag kept it `False` even while every
metric that actually gates fragility sat at `coverage_ratio = 1.000`.

Measured on the live runtime, 2026-08-11:

    healthy: False
    OK  funding_rate_settled     ratio=1.000
    OK  open_interest_value_1h   ratio=1.000
    RED order_book_spread_bps    ratio=0.091   <- live_only, backfill impossible
    RED spot_perp_basis          ratio=0.090   <- live_only, backfill impossible
"""

from datetime import UTC, datetime, timedelta

from btc_radar.core.coverage import MetricCoverage

AS_OF = datetime(2026, 8, 11, tzinfo=UTC)


def _coverage(**overrides) -> MetricCoverage:
    base = dict(
        metric="spot_perp_basis",
        history_mode="live_only",
        window_seconds=604800.0,
        expected_period_seconds=3600.0,
        expected_samples=168,
        observed_samples=15,
        coverage_ratio=0.09,
        max_gap_seconds=21600.0,
        tolerated_gap_seconds=900.0,
        longest_gap_start_at=None,
        longest_gap_end_at=None,
        oldest_event_at=None,
        newest_event_at=AS_OF.isoformat(),
        seconds_since_newest=60.0,
        complete=False,
        gap_ok=False,
        fresh=True,
        healthy=False,
    )
    base.update(overrides)
    return MetricCoverage(**base)


def test_live_only_metric_is_judged_on_freshness_not_on_unfixable_history():
    """Toplama başlamadan önceki boşluk için uç geçmiş sunmuyor; onarılamaz."""
    item = _coverage(complete=False, gap_ok=False, fresh=True, healthy=False)

    assert item.healthy is False  # ayrıntı gizlenmiyor
    assert item.meets_expectation is True  # ama beklenti karşılanıyor: hâlâ topluyor


def test_a_live_only_metric_that_stopped_collecting_still_fails():
    """Tazelik gerçek soru: durmuş bir toplayıcı sağlıklı sayılamaz."""
    item = _coverage(fresh=False)

    assert item.meets_expectation is False


def test_backfillable_metric_still_requires_full_health():
    """Geçmişi doldurulabilen metrikte boşluk gerçek bir kusurdur; tolere edilmez."""
    item = _coverage(
        metric="funding_rate_settled",
        history_mode="backfill_and_live",
        gap_ok=False,
        fresh=True,
        healthy=False,
    )

    assert item.meets_expectation is False


def test_healthy_backfillable_metric_meets_expectation():
    item = _coverage(
        metric="funding_rate_settled",
        history_mode="backfill_and_live",
        complete=True,
        gap_ok=True,
        fresh=True,
        healthy=True,
    )

    assert item.meets_expectation is True


def test_payload_exposes_both_so_nothing_is_hidden():
    """Genel bayrağın neye baktığı değişti; ayrıntı raporda aynen duruyor."""
    payload = _coverage().as_payload()

    assert payload["healthy"] is False
    assert payload["gap_ok"] is False
    assert payload["coverage_ratio"] == 0.09
    assert payload["meets_expectation"] is True
    assert payload["history_mode"] == "live_only"


def test_the_live_runtime_situation_now_reports_healthy():
    """11 Ağustos'taki gerçek tablo: iki feature mükemmel, iki live_only taze."""
    coverage = [
        _coverage(
            metric="funding_rate_settled",
            history_mode="backfill_and_live",
            complete=True,
            gap_ok=True,
            fresh=True,
            healthy=True,
        ),
        _coverage(
            metric="open_interest_value_1h",
            history_mode="backfill_and_live",
            complete=True,
            gap_ok=True,
            fresh=True,
            healthy=True,
        ),
        _coverage(metric="order_book_spread_bps"),
        _coverage(metric="spot_perp_basis"),
    ]

    # Eski kural: all(healthy) -> False (kalıcı olarak)
    assert all(item.healthy for item in coverage) is False
    # Yeni kural: beklenti karşılanıyor mu
    assert all(item.meets_expectation for item in coverage) is True


def test_a_broken_feature_still_turns_the_overall_flag_false():
    """Düzeltme bayrağı gevşetmiyor: gerçek kusur hâlâ yakalanıyor."""
    coverage = [
        _coverage(
            metric="funding_rate_settled",
            history_mode="backfill_and_live",
            gap_ok=False,
            healthy=False,
        ),
        _coverage(metric="spot_perp_basis"),
    ]

    assert all(item.meets_expectation for item in coverage) is False


# --- ADR-0012: kapanmış-mum metriğinde yarım periyot beklentiye girmez ------------------


def _store_with_hourly(rows: int, *, metric: str, end: datetime):
    """Bellek içi PIT'e `rows` adet saatlik gözlem yaz; sonuncusu `end`."""
    from btc_radar.core.store import PointInTimeStore
    from btc_radar.models.observation import RawObservation

    store = PointInTimeStore()
    observations = [
        RawObservation(
            timestamp_utc=end - timedelta(hours=index),
            retrieved_at_utc=end - timedelta(hours=index),
            available_at_utc=end - timedelta(hours=index),
            asset="BTC",
            venue="binance_spot",
            metric=metric,
            raw_value=100.0 + index,
            unit="USDT",
            source_group="spot",
            source_url="https://example.invalid",
            quality=1.0,
        )
        for index in range(rows)
    ]
    store.append(observations, provider="test")
    return store


def test_closed_bar_metric_is_not_marked_incomplete_for_the_in_progress_period():
    """Gerçek durum: 11:17'de en yeni kapanmış saatlik mum 10:00'dır.

    Sayaç içinde bulunduğumuz saati beklentiye katarsa metrik KALICI olarak eksik görünür
    ve `healthy` hiçbir zaman True olamaz.
    """
    from btc_radar.core.coverage import metric_coverage

    as_of = datetime(2026, 8, 11, 11, 17, tzinfo=UTC)
    last_closed = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    window = 24 * 3600.0
    with _store_with_hourly(24, metric="spot_close", end=last_closed) as store:
        closed = metric_coverage(
            store,
            metric="spot_close",
            asset="BTC",
            as_of=as_of,
            window_seconds=window,
            expected_period_seconds=3600.0,
            tolerated_gap_seconds=10800.0,
            history_mode="backfill_and_live",
            sampling_mode="closed_bar",
        )
        snapshot = metric_coverage(
            store,
            metric="spot_close",
            asset="BTC",
            as_of=as_of,
            window_seconds=window,
            expected_period_seconds=3600.0,
            tolerated_gap_seconds=10800.0,
            history_mode="backfill_and_live",
            sampling_mode="snapshot",
        )

    # Aynı veri: snapshot sayacı yarım saati bekler ve eksik görür, closed_bar görmez.
    assert snapshot.expected_samples == closed.expected_samples + 1
    assert closed.complete is True
    assert closed.meets_expectation is True
    assert snapshot.complete is False


def test_closed_bar_metric_with_a_real_gap_still_fails():
    """Muafiyet yalnız YARIM periyoda; gerçek eksik saat hâlâ yakalanır."""
    from btc_radar.core.coverage import metric_coverage

    as_of = datetime(2026, 8, 11, 11, 17, tzinfo=UTC)
    last_closed = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    with _store_with_hourly(20, metric="spot_close", end=last_closed) as store:
        item = metric_coverage(
            store,
            metric="spot_close",
            asset="BTC",
            as_of=as_of,
            window_seconds=24 * 3600.0,
            expected_period_seconds=3600.0,
            tolerated_gap_seconds=10800.0,
            history_mode="backfill_and_live",
            sampling_mode="closed_bar",
        )

    assert item.observed_samples == 20
    assert item.expected_samples == 23
    assert item.complete is False
    assert item.meets_expectation is False
