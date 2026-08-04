"""Snapshot değişmezliği + REPLAY DETERMİNİZMİ (CR-002 P0-1 kabul testi).

Kabul kriteri: aynı snapshot + aynı commit ile 100 replay → skor/gerekçe bit-bit özdeş.

Not: `component_builder` Faz 1'de signal_rules.yaml'dan üretilecektir. Buradaki test
builder'ı gerçekçidir (f tazelikten, q satırdan, u çift-sayım grubundan, d/r sabit
kural tablosundan gelir) ve tüm yolu — depo → bileşen → toplama → snapshot → hash —
uçtan uca zorlar. Faz 1 gerçek builder'ı taktığında bu test yerinde kalır.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.config import load_weights, weights_hash
from btc_radar.core.scoring import ScoreComponent
from btc_radar.core.snapshot import (
    SnapshotStore,
    compute_snapshot,
    content_hash_of,
    freshness,
    input_digest,
    snapshot_id_of,
    verify_regime_snapshot,
)
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.observation import RawObservation

AS_OF = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)

# Test kural tablosu: metrik → (katman, d, r, beklenen periyot sn, bağımsızlık grubu)
RULES = {
    "funding_rate": ("derivatives", 1.5, 1.0, 3600, "derivatives_binance"),
    "open_interest": ("derivatives", 0.5, 2.0, 3600, "derivatives_binance"),
    "sth_sopr": ("onchain", -1.0, 1.0, 86400, "onchain_bgeo"),
    "coinbase_premium": ("spot_regional", 2.0, 0.0, 300, "spot"),
    "fear_greed": ("cycle_sentiment", -0.5, 1.0, 86400, "sentiment"),
}


def build_components(rows: list[dict], as_of: datetime) -> list[ScoreComponent]:
    weights = load_weights()
    stale_multiple = weights.freshness.stale_multiple
    group_counts: dict[str, int] = {}
    for r in rows:
        rule = RULES.get(r["metric"])
        if rule:
            group_counts[rule[4]] = group_counts.get(rule[4], 0) + 1

    components = []
    for r in sorted(rows, key=lambda x: (x["metric"], x["asset"], x["venue"])):
        rule = RULES.get(r["metric"])
        if not rule:
            continue  # kuralsız metrik skora girmez (kapsam eksikliği güveni düşürür)
        layer, d, rr, period, group = rule
        f = freshness(
            as_of=as_of,
            event_time=datetime.fromisoformat(r["event_time"]),
            expected_period_seconds=period,
            stale_multiple=stale_multiple,
        )
        # Çift sayım: aynı bağımsızlık grubundaki n kaynak toplam 1 oy taşır (§5.5)
        u = 1.0 / group_counts[group]
        components.append(
            ScoreComponent(
                layer=layer, metric=r["metric"], d=d, r=rr, q=float(r["quality"]), f=f, u=u
            )
        )
    return components


def _obs(metric: str, value: float, *, age_minutes: int = 5, quality: float = 0.9):
    event_time = AS_OF - timedelta(minutes=age_minutes)
    return RawObservation(
        timestamp_utc=event_time,
        retrieved_at_utc=event_time + timedelta(seconds=30),
        available_at_utc=event_time + timedelta(seconds=30),
        asset="BTC",
        venue="binance_futures",
        metric=metric,
        raw_value=value,
        unit="x",
        source_group="test",
        source_url="https://example.invalid/x",
        quality=quality,
    )


def _seed_store() -> PointInTimeStore:
    store = PointInTimeStore()
    store.append(
        [
            _obs("funding_rate", 0.00031),
            _obs("open_interest", 95123.5),
            _obs("sth_sopr", 1.0005, age_minutes=600),
            _obs("coinbase_premium", 0.042, age_minutes=2),
            _obs("fear_greed", 61.0, age_minutes=300),
            # Kural tablosunda olmayan metrik: skora girmez ama depoda durur
            _obs("mystery_metric", 42.0),
        ],
        provider="test",
    )
    return store


def _make_snapshot(store: PointInTimeStore):
    rows = store.read_as_of(AS_OF)
    return compute_snapshot(
        rows,
        as_of=AS_OF,
        weights=load_weights(),
        weights_hash=weights_hash(),
        component_builder=build_components,
    )


@pytest.fixture
def store():
    s = _seed_store()
    yield s
    s.close()


def test_snapshot_has_scores_and_versions(store):
    snap = _make_snapshot(store)
    assert snap.snapshot_id.startswith("SNAP-")
    assert snap.direction is not None and -100 <= snap.direction <= 100
    assert snap.fragility is not None and 0 <= snap.fragility <= 100
    assert snap.data_cutoff_at == AS_OF
    assert snap.feature_version and snap.scoring_version and snap.weights_hash
    assert "news_catalyst" in snap.missing_layers  # MVP'de ölçülmeyen katman


def test_replay_determinism_100x():
    """KABUL TESTİ: 100 replay → bit-bit özdeş snapshot."""
    ids, hashes, payloads = set(), set(), set()
    for _ in range(100):
        s = _seed_store()  # her turda taze depo: yazma sırası/rowid etkisi de test edilir
        snap = _make_snapshot(s)
        ids.add(snap.snapshot_id)
        hashes.add(snap.content_hash)
        payloads.add(
            snap.model_dump_json(exclude={"computed_at"})  # duvar saati hariç
        )
        s.close()
    assert len(ids) == 1, f"snapshot_id kararsız: {ids}"
    assert len(hashes) == 1, f"content_hash kararsız: {hashes}"
    assert len(payloads) == 1, "skor/gerekçe gövdesi replay'ler arasında değişti"


def test_computed_at_does_not_affect_identity(store):
    rows = store.read_as_of(AS_OF)
    kwargs = dict(
        as_of=AS_OF,
        weights=load_weights(),
        weights_hash=weights_hash(),
        component_builder=build_components,
    )
    a = compute_snapshot(rows, computed_at=datetime(2026, 8, 3, 12, 1, tzinfo=UTC), **kwargs)
    b = compute_snapshot(rows, computed_at=datetime(2027, 1, 1, 0, 0, tzinfo=UTC), **kwargs)
    assert a.snapshot_id == b.snapshot_id
    assert a.content_hash == b.content_hash


def test_different_data_gives_different_snapshot_id(store):
    base = _make_snapshot(store)
    store.append([_obs("funding_rate", 0.00099, age_minutes=1)], provider="test")
    changed = _make_snapshot(store)
    assert base.snapshot_id != changed.snapshot_id


def test_store_put_is_idempotent(store):
    snap = _make_snapshot(store)
    with SnapshotStore() as snaps:
        assert snaps.put(snap) is True
        assert snaps.put(snap) is False  # aynı içerik → sessiz geçiş
        assert snaps.count() == 1


def test_concurrent_store_put_is_idempotent_across_connections(store, tmp_path):
    snap = _make_snapshot(store)
    database = tmp_path / "snapshots.sqlite"
    with SnapshotStore(database):
        pass

    def put_once(_index: int) -> bool:
        with SnapshotStore(database) as snapshots:
            return snapshots.put(snap)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(put_once, range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7
    with SnapshotStore(database) as snapshots:
        assert snapshots.count() == 1


def test_tampered_payload_rejected(store):
    """Gövdesi değişmiş ama eski hash'i taşıyan kayıt yazılamaz (depo hash'e güvenmez)."""
    snap = _make_snapshot(store)
    tampered = snap.model_copy(update={"direction": 99.0})
    with SnapshotStore() as snaps:
        with pytest.raises(ValueError, match="İÇERİK HASH UYUŞMUYOR"):
            snaps.put(tampered)
        assert snaps.count() == 0


def test_same_id_different_content_is_immutability_violation(store):
    """Aynı girdi kimliği + farklı skor = sürümsüz kod değişikliği; yazma reddedilir."""
    snap = _make_snapshot(store)
    rewritten = snap.model_copy(update={"direction": 99.0})
    rewritten = rewritten.model_copy(update={"content_hash": content_hash_of(rewritten)})
    with SnapshotStore() as snaps:
        snaps.put(snap)
        with pytest.raises(ValueError, match="DEĞİŞMEZLİK İHLALİ"):
            snaps.put(rewritten)
        assert snaps.count() == 1


def test_rehashed_fake_snapshot_id_is_rejected(store):
    snap = _make_snapshot(store)
    forged = snap.model_copy(update={"snapshot_id": "SNAP-0000000000000000"})
    forged = forged.model_copy(update={"content_hash": content_hash_of(forged)})
    assert snapshot_id_of(forged) != forged.snapshot_id
    with pytest.raises(ValueError, match="SNAPSHOT KİMLİK UYUŞMUYOR"):
        verify_regime_snapshot(forged)


def test_cutoff_tampering_is_rejected_even_with_rehashed_content(store):
    snap = _make_snapshot(store)
    forged = snap.model_copy(update={"data_cutoff_at": AS_OF - timedelta(hours=1)})
    forged = forged.model_copy(update={"content_hash": content_hash_of(forged)})
    with pytest.raises(ValueError, match="data_cutoff_at tam olarak as_of"):
        verify_regime_snapshot(forged)


def test_legacy_v01_content_hash_remains_readable(store):
    current = _make_snapshot(store)
    legacy = current.model_copy(update={"feature_version": "0.1.0", "snapshot_id": ""})
    legacy = legacy.model_copy(update={"snapshot_id": snapshot_id_of(legacy)})
    legacy = legacy.model_copy(update={"content_hash": content_hash_of(legacy)})

    with SnapshotStore() as snapshots:
        assert snapshots.put(legacy) is True
        assert snapshots.get(legacy.snapshot_id) == legacy


def test_generic_snapshot_store_accepts_non_hour_boundary(store):
    as_of = AS_OF + timedelta(minutes=15)
    snapshot = compute_snapshot(
        store.read_as_of(as_of),
        as_of=as_of,
        weights=load_weights(),
        weights_hash=weights_hash(),
        component_builder=build_components,
        computed_at=as_of + timedelta(seconds=1),
    )
    with SnapshotStore() as snapshots:
        assert snapshots.put(snapshot) is True
        assert snapshots.get_as_of(as_of) == snapshot


def test_breakdown_rejects_non_json_nested_tuple(store):
    snapshot = _make_snapshot(store)
    forged = snapshot.model_copy(update={"breakdown": [{"nested": (float("nan"),)}]})
    forged = forged.model_copy(update={"content_hash": content_hash_of(forged)})
    with pytest.raises(ValueError, match="JSON-uyumlu tür"):
        verify_regime_snapshot(forged)


def test_snapshot_roundtrip_by_id_and_as_of(store):
    snap = _make_snapshot(store)
    with SnapshotStore() as snaps:
        snaps.put(snap)
        assert snaps.get(snap.snapshot_id).content_hash == snap.content_hash
        assert snaps.get_as_of(AS_OF).snapshot_id == snap.snapshot_id
        assert snaps.get_as_of(AS_OF + timedelta(minutes=15)) is None  # "latest" yok


def test_snapshot_read_rejects_column_payload_mismatch(store):
    snap = _make_snapshot(store)
    with SnapshotStore() as snaps:
        snaps.put(snap)
        snaps._conn.execute(
            "UPDATE snapshots SET data_cutoff_at = ? WHERE snapshot_id = ?",
            ((AS_OF - timedelta(hours=1)).isoformat(timespec="microseconds"), snap.snapshot_id),
        )
        snaps._conn.commit()
        with pytest.raises(ValueError, match="data_cutoff_at kolonu payload"):
            snaps.get(snap.snapshot_id)


def test_get_as_of_rejects_naive_datetime():
    with SnapshotStore() as snaps:
        with pytest.raises(ValueError, match="timezone-aware"):
            snaps.get_as_of(datetime(2026, 8, 3, 12, 0))


def test_snapshot_excludes_data_published_after_as_of():
    """as_of'tan SONRA yayımlanan veri snapshot'a giremez (look-ahead)."""
    store = _seed_store()
    late = _obs("coinbase_premium", 9.99, age_minutes=1)
    late = late.model_copy(update={"available_at_utc": AS_OF + timedelta(minutes=10)})
    store.append([late], provider="test")
    snap = _make_snapshot(store)
    premiums = [b for b in snap.breakdown if b["metric"] == "coinbase_premium"]
    assert len(premiums) == 1
    assert _make_snapshot(_seed_store()).content_hash == snap.content_hash
    store.close()


def test_freshness_curve():
    now = AS_OF
    assert (
        freshness(as_of=now, event_time=now, expected_period_seconds=3600, stale_multiple=3.0)
        == 1.0
    )
    # tam periyot sınırında hâlâ taze
    assert (
        freshness(
            as_of=now,
            event_time=now - timedelta(seconds=3600),
            expected_period_seconds=3600,
            stale_multiple=3.0,
        )
        == 1.0
    )
    # periyodun 2 katı yaş → yarı yol (3600..7200 arası doğrusal 1→0)
    assert freshness(
        as_of=now,
        event_time=now - timedelta(seconds=7200),
        expected_period_seconds=3600,
        stale_multiple=3.0,
    ) == pytest.approx(0.5)
    # stale_multiple × periyot ve ötesi → 0
    assert (
        freshness(
            as_of=now,
            event_time=now - timedelta(seconds=99999),
            expected_period_seconds=3600,
            stale_multiple=3.0,
        )
        == 0.0
    )


def test_future_data_fails_loud():
    with pytest.raises(ValueError, match="gelecekten veri"):
        freshness(
            as_of=AS_OF,
            event_time=AS_OF + timedelta(minutes=1),
            expected_period_seconds=3600,
            stale_multiple=3.0,
        )


def test_input_digest_ignores_ingestion_metadata():
    rows = [
        {"id": 1, "ingested_at": "2026-08-03T12:00:00+00:00", "metric": "m", "raw_value": 1.0},
    ]
    other = [
        {"id": 99, "ingested_at": "2027-01-01T00:00:00+00:00", "metric": "m", "raw_value": 1.0},
    ]
    assert input_digest(rows) == input_digest(other)
