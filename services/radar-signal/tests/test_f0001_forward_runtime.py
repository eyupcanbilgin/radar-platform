"""Synthetic integration tests for the hourly runtime's optional F-0001 observer."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from decision_engine.forward_trigger import ForwardTriggerLedger
from scripts import run_hourly_decision as hourly_cli
from scripts.fragility_calibration import load_fragility_config

CONTEXT_FIXTURE = (
    hourly_cli.SERVICE_ROOT.parents[1]
    / "contracts"
    / "decision-context"
    / "v1"
    / "examples"
    / "btc-1h-context.json"
)


def _context(as_of: datetime, fragility: float) -> dict:
    payload = json.loads(CONTEXT_FIXTURE.read_text(encoding="utf-8"))
    stamp = as_of.isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(stamp.encode()).hexdigest()
    payload["as_of_utc"] = stamp
    payload["snapshot"].update(
        snapshot_id="SNAP-" + digest[:16],
        data_cutoff_at_utc=stamp,
        computed_at_utc=stamp,
        direction=None,
        fragility=fragility,
        content_hash=digest,
    )
    payload["data_quality"]["directional_decision_allowed"] = False
    payload["data_quality"]["status"] = "unavailable"
    payload["data_quality"]["blockers"] = ["direction_rules_unavailable"]
    payload["data_quality"]["warnings"] = []
    return payload


def _configs(start: datetime) -> tuple[dict, dict]:
    calibration = copy.deepcopy(load_fragility_config())
    calibration["trigger"].update(
        rolling_lookback_days=10,
        min_history_days=1,
        min_observations=24,
        episode_cooldown_hours=6,
    )
    observation = {
        "observation_start_utc": start.isoformat().replace("+00:00", "Z"),
        "baseline_context_set_sha256": "a" * 64,
    }
    return calibration, observation


def test_hourly_result_records_forward_context_after_start(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    baseline_start = start - timedelta(hours=120)
    baseline = [_context(baseline_start + timedelta(hours=i), float(i % 101)) for i in range(120)]
    current = _context(start, 90.0)
    decision_ledger = SimpleNamespace(get=lambda _decision_id: {"context_payload": current})
    result = SimpleNamespace(as_of_utc=start, decision=SimpleNamespace(decision_id="D-1"))
    calibration, observation = _configs(start)

    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as trigger_ledger:
        output = hourly_cli._observe_forward_result(
            result=result,
            decision_ledger=decision_ledger,
            trigger_ledger=trigger_ledger,
            baseline_contexts=baseline,
            calibration_config=calibration,
            observation_config=observation,
        )
        assert output["recorded"] is True
        assert output["direction"] is None
        assert output["outcome_read"] is False
        assert trigger_ledger.count() == 1


def test_hourly_forward_observer_skips_prestart_and_missing_context(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    calibration, observation = _configs(start)
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as trigger_ledger:
        before = hourly_cli._observe_forward_result(
            result=SimpleNamespace(
                as_of_utc=start - timedelta(hours=1),
                decision=SimpleNamespace(decision_id="D-before"),
            ),
            decision_ledger=SimpleNamespace(get=lambda _: None),
            trigger_ledger=trigger_ledger,
            baseline_contexts=[],
            calibration_config=calibration,
            observation_config=observation,
        )
        missing = hourly_cli._observe_forward_result(
            result=SimpleNamespace(
                as_of_utc=start,
                decision=SimpleNamespace(decision_id="D-missing"),
            ),
            decision_ledger=SimpleNamespace(get=lambda _: {"context_payload": None}),
            trigger_ledger=trigger_ledger,
            baseline_contexts=[],
            calibration_config=calibration,
            observation_config=observation,
        )

        assert before == {"status": "before_start", "recorded": False, "direction": None}
        assert missing["status"] == "context_unavailable"
        assert missing["recorded"] is False
        assert trigger_ledger.count() == 0
