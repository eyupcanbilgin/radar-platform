"""Synthetic tests for the outcome-blind F-0001 forward trigger ledger."""

import copy
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from decision_engine.forward_trigger import (
    ForwardTriggerLedger,
    ImmutableTriggerObservationError,
    build_forward_observation,
)
from enricher.decision_context import DecisionContextV1
from scripts.fragility_calibration import load_fragility_config


def _payload(as_of: datetime, fragility: float | None = 90.0, *, suffix: str = "0") -> dict:
    stamp = as_of.isoformat().replace("+00:00", "Z")
    blockers = [] if fragility is not None else ["feature_unavailable:fragility"]
    return {
        "schema_version": "decision-context/v1",
        "instrument": {
            "asset": "BTC",
            "symbol": "BTCUSDT",
            "market": "USDT_PERPETUAL",
            "venue": "binance",
            "timeframe": "1h",
        },
        "as_of_utc": stamp,
        "snapshot": {
            "snapshot_id": f"SNAP-{suffix * 16}",
            "data_cutoff_at_utc": stamp,
            "computed_at_utc": stamp,
            "direction": None,
            "fragility": fragility,
            "confidence": 0.0,
            "regime_label": "veri_yetersiz",
            "feature_version": "test",
            "scoring_version": "test",
            "weights_hash": "a" * 12,
            "input_digest": "b" * 64,
            "content_hash": suffix * 64,
        },
        "data_quality": {
            "status": "unavailable",
            "directional_decision_allowed": False,
            "stale_sources": [],
            "missing_layers": [],
            "blockers": blockers or ["direction_rules_unavailable"],
            "warnings": [],
        },
        "usage": {
            "decision_role": "context_only",
            "allowed_outputs": ["LONG", "SHORT", "WAIT"],
            "mode": "paper",
            "real_orders": False,
        },
    }


def _baseline(hours: int = 120) -> list[dict]:
    start = datetime(2026, 8, 2, tzinfo=UTC)
    return [
        _payload(start + timedelta(hours=index), float((index * 17) % 101), suffix="a")
        for index in range(hours)
    ]


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
        "baseline_context_set_sha256": "c" * 64,
    }
    return calibration, observation


def _observation(context, *, baseline=None, previous=None, prior=None):
    calibration, observation = _configs(context.as_of_utc)
    return build_forward_observation(
        baseline_contexts=baseline or _baseline(),
        prior_contexts=prior or [],
        context=context,
        calibration_config=calibration,
        observation_config=observation,
        previous_as_of_utc=previous,
    )


def test_records_exact_retry_idempotently_and_rejects_conflict(tmp_path):
    as_of = datetime(2026, 8, 7, tzinfo=UTC)
    context = DecisionContextV1.model_validate(_payload(as_of, suffix="d"))
    observation = _observation(context)
    path = tmp_path / "forward.sqlite"

    with ForwardTriggerLedger(path) as ledger:
        assert ledger.record(observation, context, recorded_at_utc=as_of)
        assert not ledger.record(observation, context, recorded_at_utc=as_of)
        assert ledger.count() == 1
        assert ledger.get(as_of)["payload"] == observation

        changed = dict(observation, blockers=["changed"])
        with pytest.raises(ImmutableTriggerObservationError, match="yeniden yazılamaz"):
            ledger.record(changed, context, recorded_at_utc=as_of)


def test_sqlite_update_and_delete_are_blocked(tmp_path):
    as_of = datetime(2026, 8, 7, tzinfo=UTC)
    context = DecisionContextV1.model_validate(_payload(as_of, suffix="d"))
    observation = _observation(context)
    with ForwardTriggerLedger(tmp_path / "forward.sqlite") as ledger:
        ledger.record(observation, context, recorded_at_utc=as_of)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger._conn.execute("UPDATE f0001_trigger_observations SET status='unavailable'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger._conn.execute("DELETE FROM f0001_trigger_observations")


def test_null_fragility_is_unavailable_not_false_trigger():
    as_of = datetime(2026, 8, 7, tzinfo=UTC)
    context = DecisionContextV1.model_validate(_payload(as_of, fragility=None, suffix="d"))
    observation = _observation(context)

    assert observation["status"] == "unavailable"
    assert observation["triggered"] is None
    assert "fragility_unavailable" in observation["blockers"]
    assert observation["direction"] is None
    assert observation["outcome_read"] is False
    assert observation["registry_write"] is False
    assert observation["alert_emitted"] is False


def test_prestart_backfill_is_rejected_and_forward_gap_is_reported():
    start = datetime(2026, 8, 7, tzinfo=UTC)
    calibration, observation_config = _configs(start)
    old = DecisionContextV1.model_validate(_payload(start - timedelta(hours=1), suffix="d"))
    with pytest.raises(ValueError, match="backfill yasak"):
        build_forward_observation(
            baseline_contexts=_baseline(),
            prior_contexts=[],
            context=old,
            calibration_config=calibration,
            observation_config=observation_config,
            previous_as_of_utc=None,
        )

    late = DecisionContextV1.model_validate(_payload(start + timedelta(hours=3), suffix="e"))
    result = build_forward_observation(
        baseline_contexts=_baseline(),
        prior_contexts=[],
        context=late,
        calibration_config=calibration,
        observation_config=observation_config,
        previous_as_of_utc=None,
    )
    assert result["gap_hours"] == 3
    assert "missing_forward_hours:3" in result["blockers"]
