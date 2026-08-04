import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.config import load_weights, weights_hash
from btc_radar.core.context_publisher import (
    ContextPublishError,
    CorruptContextArtifactError,
    ExactHourContextPublisher,
    ImmutableContextConflictError,
)
from btc_radar.core.snapshot import compute_snapshot
from btc_radar.models.decision_context import DecisionContextV1
from btc_radar.models.observation import RawObservation

AS_OF = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _row(*, value: float = 95_000.0) -> dict:
    observation = RawObservation(
        timestamp_utc=AS_OF - timedelta(minutes=1),
        retrieved_at_utc=AS_OF - timedelta(seconds=30),
        asset="BTC",
        venue="binance_futures",
        metric="open_interest",
        raw_value=value,
        unit="BTC",
        source_group="derivatives",
        source_url="https://fapi.binance.com/fapi/v1/openInterest",
        quality=1.0,
    )
    return {
        "event_time": observation.timestamp_utc.isoformat(timespec="microseconds"),
        "available_at": observation.effective_available_at.isoformat(timespec="microseconds"),
        "provider": "binance_usdm",
        "schema_version": "1",
        "payload_hash": "a" * 64,
        "asset": observation.asset,
        "venue": observation.venue,
        "metric": observation.metric,
        "raw_value": observation.raw_value,
        "unit": observation.unit,
        "window": observation.window,
        "source_group": observation.source_group,
        "source_url": observation.source_url,
        "quality": observation.quality,
        "notes": observation.notes,
    }


def _snapshot(
    *,
    computed_at: datetime = AS_OF + timedelta(seconds=5),
    value: float = 95_000.0,
):
    return compute_snapshot(
        [_row(value=value)],
        as_of=AS_OF,
        weights=load_weights(),
        weights_hash=weights_hash(),
        component_builder=lambda _rows, _as_of: [],
        computed_at=computed_at,
    )


def _publish(publisher: ExactHourContextPublisher, snapshot=None):
    return publisher.publish(
        snapshot or _snapshot(),
        required_layers=frozenset({"derivatives"}),
        additional_blockers=frozenset({"scoring_rules_unavailable"}),
    )


def test_publish_creates_exact_hour_valid_unavailable_context(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    result = _publish(publisher)

    assert result.status == "created"
    assert result.path == tmp_path / "v1/BTCUSDT/1h/2026/08/03/12.json"
    context = DecisionContextV1.model_validate_json(result.path.read_bytes())
    assert context.as_of_utc == AS_OF
    assert context.data_quality.status == "unavailable"
    assert context.data_quality.directional_decision_allowed is False
    assert context.data_quality.blockers == [
        "missing_required_layer:derivatives",
        "regime_unavailable",
        "scores_unavailable",
        "scoring_rules_unavailable",
    ]


def test_same_publish_is_idempotent_without_touching_bytes_or_mtime(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    first = _publish(publisher)
    before = first.path.read_bytes(), first.path.stat().st_mtime_ns

    second = _publish(publisher)

    assert second.status == "idempotent"
    assert (first.path.read_bytes(), first.path.stat().st_mtime_ns) == before


def test_only_computed_at_difference_is_semantically_idempotent(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    first = _publish(publisher, _snapshot(computed_at=AS_OF + timedelta(seconds=5)))
    before = first.path.read_bytes()

    second = _publish(publisher, _snapshot(computed_at=AS_OF + timedelta(minutes=10)))

    assert second.status == "idempotent"
    assert first.path.read_bytes() == before


def test_different_snapshot_for_same_hour_conflicts(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    _publish(publisher, _snapshot(value=95_000.0))

    with pytest.raises(ImmutableContextConflictError, match="DEĞİŞMEZ CONTEXT"):
        _publish(publisher, _snapshot(value=96_000.0))


def test_corrupt_existing_artifact_is_never_overwritten(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    path = publisher.path_for(as_of_utc=AS_OF)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(CorruptContextArtifactError, match="overwrite edilmeyecek"):
        _publish(publisher)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_existing_pre_as_of_computed_time_is_not_idempotent(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    created = _publish(publisher)
    payload = DecisionContextV1.model_validate_json(created.path.read_bytes()).model_dump(
        mode="json"
    )
    payload["snapshot"]["computed_at_utc"] = "2026-08-03T11:59:59Z"
    created.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorruptContextArtifactError, match="computed_at as_of öncesinde"):
        _publish(publisher)


def test_concurrent_identical_publish_has_one_creator(tmp_path):
    publisher = ExactHourContextPublisher(tmp_path)
    snapshot = _snapshot()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _index: _publish(publisher, snapshot), range(4)))

    assert sorted(result.status for result in results) == [
        "created",
        "idempotent",
        "idempotent",
        "idempotent",
    ]


def test_hardlink_failure_does_not_use_overwrite_fallback(tmp_path, monkeypatch):
    publisher = ExactHourContextPublisher(tmp_path)

    def fail_link(_source, _target):
        raise OSError("hard links unavailable")

    monkeypatch.setattr("btc_radar.core.context_publisher.os.link", fail_link)
    with pytest.raises(ContextPublishError, match="güvensiz fallback kullanılmadı"):
        _publish(publisher)
    assert not publisher.path_for(as_of_utc=AS_OF).exists()
    assert list(tmp_path.rglob("*.tmp")) == []
