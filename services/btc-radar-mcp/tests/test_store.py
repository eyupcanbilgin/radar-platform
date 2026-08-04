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
