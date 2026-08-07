"""Synthetic tests for outcome-blind F-0001 forward coverage reporting."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from decision_engine.forward_trigger import ForwardTriggerLedger, build_forward_observation
from enricher.decision_context import DecisionContextV1
from scripts.f0001_forward_coverage import build_forward_coverage_report
from scripts.f0001_forward_coverage import main as coverage_main
from scripts.fragility_calibration import load_fragility_config

CONTEXT_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "decision-context"
    / "v1"
    / "examples"
    / "btc-1h-context.json"
)


def _payload(as_of: datetime, fragility: float | None) -> dict:
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
    payload["data_quality"].update(
        directional_decision_allowed=False,
        status="unavailable",
        blockers=["direction_rules_unavailable"],
    )
    return payload


def _observation(context: DecisionContextV1) -> dict:
    calibration = copy.deepcopy(load_fragility_config())
    calibration["trigger"].update(
        rolling_lookback_days=2,
        min_history_days=1,
        min_observations=24,
        episode_cooldown_hours=6,
    )
    baseline_start = context.as_of_utc - timedelta(hours=72)
    baseline = [
        _payload(baseline_start + timedelta(hours=index), float((index * 17) % 101))
        for index in range(72)
    ]
    return build_forward_observation(
        baseline_contexts=baseline,
        prior_contexts=[],
        context=context,
        calibration_config=calibration,
        observation_config={
            "observation_start_utc": context.as_of_utc.isoformat().replace("+00:00", "Z"),
            "baseline_context_set_sha256": "c" * 64,
        },
        previous_as_of_utc=None,
    )


def _record(ledger: ForwardTriggerLedger, as_of: datetime, *, fragility=0.0) -> None:
    context = DecisionContextV1.model_validate(_payload(as_of, fragility))
    ledger.record(_observation(context), context, recorded_at_utc=as_of)


def _config(start: datetime) -> dict:
    return {
        "observation_start_utc": start.isoformat().replace("+00:00", "Z"),
        "baseline_context_set_sha256": "c" * 64,
    }


def test_complete_coverage_is_directionless_and_outcome_blind(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as ledger:
        for offset in range(3):
            _record(ledger, start + timedelta(hours=offset))
        report = build_forward_coverage_report(
            ledger=ledger,
            observation_config=_config(start),
            as_of_utc=start + timedelta(hours=2),
        )

    assert report["status"] == "ok"
    assert report["expected_hour_count"] == 3
    assert report["recorded_observation_count"] == 3
    assert report["coverage_ratio"] == 1.0
    assert report["blockers"] == []
    assert report["direction"] is None
    assert report["outcome_read"] is False
    assert report["registry_write"] is False
    assert report["alert_emitted"] is False


def test_missing_and_unavailable_hours_are_blockers_not_neutral(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as ledger:
        _record(ledger, start, fragility=None)
        report = build_forward_coverage_report(
            ledger=ledger,
            observation_config=_config(start),
            as_of_utc=start + timedelta(hours=2),
        )

    assert report["status"] == "degraded"
    assert report["recorded_observation_count"] == 1
    assert report["missing_hour_count"] == 2
    assert report["unavailable_observation_count"] == 1
    assert report["triggered_observation_count"] == 0
    assert report["not_triggered_observation_count"] == 0
    assert report["blockers"] == [
        "missing_forward_hours:2",
        "unavailable_forward_observations:1",
    ]


def test_before_start_does_not_claim_zero_coverage(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as ledger:
        report = build_forward_coverage_report(
            ledger=ledger,
            observation_config=_config(start),
            as_of_utc=start - timedelta(hours=1),
        )

    assert report["status"] == "before_start"
    assert report["expected_hour_count"] == 0
    assert report["coverage_ratio"] is None
    assert report["blockers"] == []


def test_coverage_rejects_a_ledger_from_another_baseline(tmp_path):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    config = _config(start)
    config["baseline_context_set_sha256"] = "e" * 64
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as ledger:
        _record(ledger, start)
        with pytest.raises(ValueError, match="baseline hash"):
            build_forward_coverage_report(
                ledger=ledger,
                observation_config=config,
                as_of_utc=start,
            )


def test_read_only_ledger_does_not_create_or_change_the_database(tmp_path):
    path = tmp_path / "forward.sqlite"
    with pytest.raises(FileNotFoundError, match="bulunamadı"):
        ForwardTriggerLedger(path, read_only=True)

    with ForwardTriggerLedger(path):
        pass
    before = path.read_bytes()
    with ForwardTriggerLedger(path, read_only=True) as ledger:
        assert ledger.count() == 0
    assert path.read_bytes() == before


def test_cli_writes_latest_report_atomically(tmp_path, monkeypatch, capsys):
    start = datetime(2026, 8, 7, tzinfo=UTC)
    ledger_path = tmp_path / "forward.sqlite"
    output_path = tmp_path / "status/coverage.json"
    with ForwardTriggerLedger(ledger_path) as ledger:
        _record(ledger, start)

    monkeypatch.setattr(
        "scripts.f0001_forward_coverage.load_forward_observation_config",
        lambda: _config(start),
    )
    assert (
        coverage_main(
            [
                "--ledger",
                str(ledger_path),
                "--as-of",
                "2026-08-07T00:00:00Z",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["direction"] is None
    assert not list(output_path.parent.glob("*.tmp"))
