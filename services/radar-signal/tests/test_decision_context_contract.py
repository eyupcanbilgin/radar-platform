import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from enricher.decision_context import (
    DecisionContextV1,
    directional_gate,
    parse_decision_context,
)

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = PLATFORM_ROOT / "contracts" / "decision-context" / "v1"
SCHEMA = json.loads((CONTRACT_ROOT / "schema.json").read_text(encoding="utf-8"))
FIXTURE = json.loads(
    (CONTRACT_ROOT / "examples" / "btc-1h-context.json").read_text(encoding="utf-8")
)
AS_OF = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_shared_fixture_matches_normative_json_schema():
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(FIXTURE)


def test_signal_consumer_accepts_shared_fixture_for_exact_candle():
    context = parse_decision_context(FIXTURE, expected_as_of=AS_OF)
    assert context.snapshot.snapshot_id == "SNAP-0123456789abcdef"
    assert directional_gate(context).allowed is True


def test_signal_consumer_refuses_context_from_different_candle():
    with pytest.raises(ValueError, match="decision context as_of uyuşmuyor"):
        parse_decision_context(
            FIXTURE,
            expected_as_of=datetime(2026, 8, 3, 13, 0, tzinfo=UTC),
        )


def test_required_data_blocker_forces_wait():
    payload = deepcopy(FIXTURE)
    payload["data_quality"] = {
        **payload["data_quality"],
        "status": "unavailable",
        "directional_decision_allowed": False,
        "blockers": ["missing_required_layer:derivatives"],
    }
    context = DecisionContextV1.model_validate(payload)
    gate = directional_gate(context)
    assert gate.allowed is False
    assert gate.output_when_closed == "WAIT"
    assert gate.reasons == ("missing_required_layer:derivatives",)


def test_future_data_cutoff_is_rejected_by_consumer():
    payload = deepcopy(FIXTURE)
    payload["snapshot"]["data_cutoff_at_utc"] = "2026-08-03T12:00:01Z"
    with pytest.raises(ValidationError, match="data_cutoff_at_utc as_of_utc sonrasında olamaz"):
        DecisionContextV1.model_validate(payload)


def test_unknown_wire_field_is_rejected_by_schema_and_consumer():
    payload = deepcopy(FIXTURE)
    payload["unexpected"] = True
    errors = list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(payload))
    assert errors
    with pytest.raises(ValidationError, match="unexpected"):
        DecisionContextV1.model_validate(payload)


def test_schema_and_consumer_reject_non_hourly_decision_boundary():
    payload = deepcopy(FIXTURE)
    payload["as_of_utc"] = "2026-08-03T12:15:00Z"
    assert list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(payload))
    with pytest.raises(ValidationError, match="kapanmış 1h mum sınırı"):
        DecisionContextV1.model_validate(payload)


def test_schema_rejects_incoherent_unavailable_quality_gate():
    payload = deepcopy(FIXTURE)
    payload["data_quality"]["status"] = "unavailable"
    errors = list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(payload))
    assert errors
    with pytest.raises(ValidationError, match="unavailable veri blocker taşır"):
        DecisionContextV1.model_validate(payload)
