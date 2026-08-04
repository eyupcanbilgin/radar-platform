import json
from datetime import UTC, datetime
from pathlib import Path

from btc_radar.models.decision_context import DecisionContextV1, build_decision_context
from btc_radar.models.snapshot import RegimeSnapshot

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    PLATFORM_ROOT / "contracts" / "decision-context" / "v1" / "examples" / "btc-1h-context.json"
)


def fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fixture_snapshot() -> RegimeSnapshot:
    payload = fixture_payload()
    snapshot = payload["snapshot"]
    return RegimeSnapshot(
        snapshot_id=snapshot["snapshot_id"],
        as_of=payload["as_of_utc"],
        data_cutoff_at=snapshot["data_cutoff_at_utc"],
        computed_at=snapshot["computed_at_utc"],
        direction=snapshot["direction"],
        fragility=snapshot["fragility"],
        confidence=snapshot["confidence"],
        regime_label=snapshot["regime_label"],
        feature_version=snapshot["feature_version"],
        scoring_version=snapshot["scoring_version"],
        weights_hash=snapshot["weights_hash"],
        input_digest=snapshot["input_digest"],
        content_hash=snapshot["content_hash"],
        missing_layers=payload["data_quality"]["missing_layers"],
    )


def test_shared_fixture_is_accepted_by_mcp_producer_model():
    context = DecisionContextV1.model_validate(fixture_payload())
    assert context.instrument.timeframe == "1h"
    assert context.usage.real_orders is False


def test_snapshot_adapter_matches_shared_fixture_exactly():
    context = build_decision_context(fixture_snapshot())
    assert context.model_dump(mode="json") == fixture_payload()


def test_missing_required_layer_closes_directional_gate():
    context = build_decision_context(
        fixture_snapshot(), required_layers=frozenset({"news_catalyst"})
    )
    assert context.data_quality.status == "unavailable"
    assert context.data_quality.directional_decision_allowed is False
    assert context.data_quality.blockers == ["missing_required_layer:news_catalyst"]


def test_snapshot_cutoff_after_as_of_is_rejected():
    payload = fixture_payload()
    payload["snapshot"]["data_cutoff_at_utc"] = "2026-08-03T12:00:01Z"
    try:
        DecisionContextV1.model_validate(payload)
    except ValueError as exc:
        assert "data_cutoff_at_utc as_of_utc sonrasında olamaz" in str(exc)
    else:
        raise AssertionError("future cutoff kabul edilmemeliydi")


def test_fixture_timestamp_is_utc_aware():
    context = DecisionContextV1.model_validate(fixture_payload())
    assert context.as_of_utc == datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_non_hourly_decision_boundary_is_rejected():
    payload = fixture_payload()
    payload["as_of_utc"] = "2026-08-03T12:15:00Z"
    try:
        DecisionContextV1.model_validate(payload)
    except ValueError as exc:
        assert "kapanmış 1h mum sınırı" in str(exc)
    else:
        raise AssertionError("15m sınırı BTC 1h sözleşmesine girmemeliydi")
