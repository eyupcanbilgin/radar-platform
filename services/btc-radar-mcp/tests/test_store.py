"""PIT depo sözleşme testleri (CR-002 P0-1): look-ahead depo katmanında imkânsız."""

from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.store import PointInTimeStore, payload_hash
from btc_radar.models.observation import RawObservation

T0 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _obs(**over) -> RawObservation:
    base = dict(
        timestamp_utc=T0,
        retrieved_at_utc=T0 + timedelta(minutes=1),
        asset="BTC",
        venue="binance_futures",
        metric="open_interest",
        raw_value=95000.0,
        unit="BTC",
        source_group="derivatives",
        source_url="https://fapi.binance.com/fapi/v1/openInterest",
        quality=0.95,
    )
    base.update(over)
    return RawObservation(**base)


@pytest.fixture
def store():
    with PointInTimeStore() as s:
        yield s


def test_append_and_count(store):
    assert store.append([_obs()], provider="binance") == 1
    assert store.count() == 1


def test_duplicate_append_is_idempotent(store):
    obs = _obs()
    store.append([obs], provider="binance")
    store.append([obs], provider="binance")
    assert store.count() == 1


def test_same_payload_at_different_knowledge_times_is_preserved(store):
    early = _obs(available_at_utc=T0 + timedelta(minutes=1))
    later = early.model_copy(update={"available_at_utc": T0 + timedelta(minutes=5)})

    assert store.append([later], provider="binance") == 1
    assert store.append([early], provider="binance") == 1
    assert store.count() == 2
    assert store.read_as_of(T0 + timedelta(minutes=2))[0]["raw_value"] == early.raw_value


def test_revision_can_return_to_an_earlier_value(store):
    revisions = [
        _obs(raw_value=1.0, available_at_utc=T0 + timedelta(minutes=1)),
        _obs(raw_value=2.0, available_at_utc=T0 + timedelta(minutes=2)),
        _obs(raw_value=1.0, available_at_utc=T0 + timedelta(minutes=3)),
    ]
    assert store.append(revisions, provider="binance") == 3
    assert store.read_as_of(T0 + timedelta(minutes=4))[0]["raw_value"] == 1.0
    history = store.revision_history(
        metric="open_interest", asset="BTC", venue="binance_futures", event_time=T0
    )
    assert [row["raw_value"] for row in history] == [1.0, 2.0, 1.0]


def test_read_as_of_hides_future_data(store):
    """available_at > as_of olan satır ASLA dönmez — look-ahead koruması."""
    store.append([_obs(available_at_utc=T0 + timedelta(minutes=30))], provider="binance")
    assert store.read_as_of(T0 + timedelta(minutes=10)) == []
    assert len(store.read_as_of(T0 + timedelta(minutes=31))) == 1


def test_available_at_defaults_to_retrieved_at(store):
    """available_at verilmezse çekim anı kullanılır (muhafazakâr taraf)."""
    store.append([_obs()], provider="binance")
    assert store.read_as_of(T0 + timedelta(seconds=30)) == []
    assert len(store.read_as_of(T0 + timedelta(minutes=2))) == 1


def test_revision_creates_new_row_not_update(store):
    """Aynı olay anı revize edilirse eski kayıt korunur; as_of'a göre doğru sürüm seçilir."""
    first = _obs(raw_value=95000.0, available_at_utc=T0 + timedelta(minutes=1))
    revised = _obs(raw_value=96000.0, available_at_utc=T0 + timedelta(hours=6))
    store.append([first], provider="bitcoin_data")
    store.append([revised], provider="bitcoin_data")
    assert store.count() == 2

    early = store.read_as_of(T0 + timedelta(hours=1))
    assert len(early) == 1 and early[0]["raw_value"] == 95000.0  # o gün ne biliyorduk

    late = store.read_as_of(T0 + timedelta(hours=12))
    assert len(late) == 1 and late[0]["raw_value"] == 96000.0  # revizyon sonrası

    history = store.revision_history(
        metric="open_interest", asset="BTC", venue="binance_futures", event_time=T0
    )
    assert [h["raw_value"] for h in history] == [95000.0, 96000.0]


def test_latest_event_time_wins(store):
    store.append(
        [
            _obs(timestamp_utc=T0, available_at_utc=T0 + timedelta(minutes=1), raw_value=1.0),
            _obs(
                timestamp_utc=T0 + timedelta(minutes=15),
                available_at_utc=T0 + timedelta(minutes=16),
                raw_value=2.0,
            ),
        ],
        provider="binance",
    )
    rows = store.read_as_of(T0 + timedelta(minutes=20))
    assert len(rows) == 1 and rows[0]["raw_value"] == 2.0


def test_read_as_of_is_deterministically_ordered(store):
    store.append(
        [
            _obs(metric="funding_rate", raw_value=0.0001),
            _obs(metric="open_interest", raw_value=95000.0),
            _obs(metric="funding_rate", venue="bybit", raw_value=0.0002),
        ],
        provider="mixed",
    )
    rows = store.read_as_of(T0 + timedelta(minutes=5))
    assert [(r["metric"], r["venue"]) for r in rows] == [
        ("funding_rate", "binance_futures"),
        ("funding_rate", "bybit"),
        ("open_interest", "binance_futures"),
    ]


def test_payload_hash_detects_value_change():
    assert payload_hash(_obs(raw_value=1.0)) != payload_hash(_obs(raw_value=2.0))
    # retrieved_at farkı içerik hash'ini DEĞİŞTİRMEZ (aynı veri, farklı çekim anı)
    assert payload_hash(_obs()) == payload_hash(_obs(retrieved_at_utc=T0 + timedelta(hours=3)))


def _series_obs(hour: int, value: float, **over) -> RawObservation:
    event = T0 + timedelta(hours=hour)
    base = dict(
        timestamp_utc=event,
        retrieved_at_utc=event + timedelta(seconds=60),
        available_at_utc=event + timedelta(seconds=60),
        metric="open_interest_1h",
        raw_value=value,
        window="1h",
    )
    base.update(over)
    return _obs(**base)


def test_read_series_returns_ascending_pit_safe_history(store):
    store.append([_series_obs(h, 100.0 + h) for h in range(5)], provider="history")

    rows = store.read_series(
        metric="open_interest_1h", asset="BTC", as_of=T0 + timedelta(hours=3, minutes=1)
    )

    assert [r["raw_value"] for r in rows] == [100.0, 101.0, 102.0, 103.0]
    assert [r["event_time"] for r in rows] == sorted(r["event_time"] for r in rows)


def test_read_series_never_shows_rows_published_after_the_cutoff(store):
    store.append([_series_obs(h, 100.0 + h) for h in range(5)], provider="history")

    # The 3h bucket is published 60s after its own timestamp, so it is invisible at 3h sharp.
    rows = store.read_series(metric="open_interest_1h", asset="BTC", as_of=T0 + timedelta(hours=3))

    assert [r["raw_value"] for r in rows] == [100.0, 101.0, 102.0]


def test_read_series_picks_the_revision_known_at_the_cutoff(store):
    event = T0 + timedelta(hours=1)
    store.append(
        [
            _series_obs(1, 10.0, available_at_utc=event + timedelta(minutes=1)),
            _series_obs(1, 20.0, available_at_utc=event + timedelta(minutes=5)),
            _series_obs(1, 30.0, available_at_utc=event + timedelta(minutes=9)),
        ],
        provider="history",
    )

    early = store.read_series(
        metric="open_interest_1h", asset="BTC", as_of=event + timedelta(minutes=6)
    )
    late = store.read_series(
        metric="open_interest_1h", asset="BTC", as_of=event + timedelta(minutes=30)
    )

    assert [r["raw_value"] for r in early] == [20.0]
    assert [r["raw_value"] for r in late] == [30.0]


def test_read_series_limit_keeps_the_newest_events(store):
    store.append([_series_obs(h, 100.0 + h) for h in range(6)], provider="history")

    rows = store.read_series(
        metric="open_interest_1h",
        asset="BTC",
        as_of=T0 + timedelta(hours=6),
        limit=2,
    )

    assert [r["raw_value"] for r in rows] == [104.0, 105.0]


def test_read_series_filters_metric_venue_and_since(store):
    store.append(
        [
            _series_obs(0, 1.0),
            _series_obs(1, 2.0),
            _series_obs(2, 3.0),
            _series_obs(2, 99.0, metric="funding_rate_settled", window=None),
            _series_obs(2, 77.0, venue="bybit_futures"),
        ],
        provider="history",
    )
    as_of = T0 + timedelta(hours=9)

    by_metric = store.read_series(metric="open_interest_1h", asset="BTC", as_of=as_of)
    by_venue = store.read_series(
        metric="open_interest_1h", asset="BTC", as_of=as_of, venue="bybit_futures"
    )
    since = store.read_series(
        metric="open_interest_1h", asset="BTC", as_of=as_of, since=T0 + timedelta(hours=2)
    )

    assert [r["raw_value"] for r in by_metric] == [1.0, 2.0, 3.0, 77.0]
    assert [r["raw_value"] for r in by_venue] == [77.0]
    assert [r["raw_value"] for r in since] == [3.0, 77.0]


def test_read_series_rejects_naive_cutoff_and_non_positive_limit(store):
    with pytest.raises(ValueError, match="timezone-aware"):
        store.read_series(metric="open_interest_1h", asset="BTC", as_of=datetime(2026, 8, 3, 12))
    with pytest.raises(ValueError, match="limit > 0"):
        store.read_series(metric="open_interest_1h", asset="BTC", as_of=T0, limit=0)
