"""Comprehensive unit tests for BTC 1h Decision Outcome Evaluator and Ledger."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from decision_engine.decision import DirectionalSetup, build_hourly_decision
from decision_engine.evaluator import evaluate_horizon_outcome
from decision_engine.features import LOOKBACK_BARS, Candle1h, build_feature_snapshot
from decision_engine.ledger import DecisionLedger, ImmutableDecisionError
from decision_engine.outcomes import (
    EVALUATOR_VERSION,
    DecisionOutcomeV1,
    OutcomeDataHealthV1,
    compute_outcome_id,
    outcome_content_hash,
    verify_decision_outcome,
)
from enricher.decision_context import DecisionContextV1

SIGNAL_COMMIT = "abcdef123456"
PLATFORM_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_FIXTURE = (
    PLATFORM_ROOT / "contracts" / "decision-context" / "v1" / "examples" / "btc-1h-context.json"
)


def context_at(as_of: datetime, *, blocked: bool = False) -> DecisionContextV1:
    payload = json.loads(CONTEXT_FIXTURE.read_text(encoding="utf-8"))
    stamp = as_of.isoformat().replace("+00:00", "Z")
    suffix = hashlib.sha256(stamp.encode()).hexdigest()
    payload["as_of_utc"] = stamp
    payload["snapshot"]["snapshot_id"] = "SNAP-" + suffix[:16]
    payload["snapshot"]["data_cutoff_at_utc"] = stamp
    payload["snapshot"]["computed_at_utc"] = (
        (as_of + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    )
    payload["snapshot"]["content_hash"] = suffix
    if blocked:
        payload["data_quality"].update(
            {
                "status": "unavailable",
                "directional_decision_allowed": False,
                "blockers": ["missing_required_layer:derivatives"],
            }
        )
    return DecisionContextV1.model_validate(payload)


def make_dummy_candles(
    start_utc: datetime,
    count: int,
    base_price: float = 50000.0,
    price_step: float = 10.0,
    high_offset: float = 50.0,
    low_offset: float = 50.0,
    available_lag_hours: int = 0,
) -> list[Candle1h]:
    candles = []
    for i in range(count):
        op_time = start_utc + timedelta(hours=i)
        cl_time = op_time + timedelta(hours=1)
        avail_time = cl_time + timedelta(hours=available_lag_hours)
        close_p = base_price + i * price_step
        candles.append(
            Candle1h(
                open_time_utc=op_time,
                close_time_utc=cl_time,
                available_at_utc=avail_time,
                open=close_p - 5.0,
                high=close_p + high_offset,
                low=close_p - low_offset,
                close=close_p,
                volume=1000.0 + i * 10,
            )
        )
    return candles


def setup_decision_fixture(
    as_of: datetime,
    outcome_direction: str = "WAIT",
) -> tuple[DecisionLedger, dict]:
    ledger = DecisionLedger()
    history_start = as_of - timedelta(hours=LOOKBACK_BARS)
    candles = make_dummy_candles(history_start, LOOKBACK_BARS)
    feature = build_feature_snapshot(candles, as_of=as_of)

    setup = None
    context = None
    if outcome_direction in {"LONG", "SHORT"}:
        setup = DirectionalSetup(
            setup_id="SETUP-TEST-01",
            hypothesis_id="S-0001",
            rule_version="1.0",
            as_of_utc=as_of,
            feature_snapshot_id=feature.snapshot_id,
            feature_content_hash=feature.content_hash,
            direction=outcome_direction,
            rationale="Test setup rationale",
            counter_evidence="Test setup counter evidence",
        )
        context = context_at(as_of)

    decision = build_hourly_decision(
        feature_snapshot=feature,
        context=context,
        setup=setup,
        signal_commit=SIGNAL_COMMIT,
    )
    ledger.record(feature=feature, context=context, decision=decision)
    return ledger, {"feature": feature, "context": context, "decision": decision}


def test_outcome_id_and_verification():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    horizon = "+1h"
    close_utc = as_of + timedelta(hours=1)
    candles = make_dummy_candles(as_of, 1)

    outcome = evaluate_horizon_outcome(
        decision=decision,
        horizon=horizon,
        candles=candles,
        evaluation_time_utc=close_utc + timedelta(minutes=5),
    )

    assert outcome.outcome_id == compute_outcome_id(
        decision_id=decision.decision_id, horizon=horizon
    )
    assert outcome.content_hash == outcome_content_hash(outcome)
    verify_decision_outcome(outcome)


def test_wait_semantics_produces_no_directional_pnl():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 4, base_price=50000.0, price_step=100.0)
    eval_time = as_of + timedelta(hours=4, minutes=5)

    outcome = evaluate_horizon_outcome(
        decision=decision,
        horizon="+4h",
        candles=candles,
        evaluation_time_utc=eval_time,
    )

    assert outcome.status == "evaluated"
    assert outcome.decision_outcome == "WAIT"
    assert outcome.raw_return is None
    assert outcome.net_return is None
    assert outcome.mfe is None
    assert outcome.mae is None
    assert outcome.opportunity_return is not None
    # Ref price: candle[0].open = 49995.0, Horizon close: candle[3].close = 50300.0
    expected_opp = (50300.0 - 49995.0) / 49995.0
    assert abs(outcome.opportunity_return - expected_opp) < 1e-9


def test_long_and_short_raw_mfe_mae_signs():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _, long_fix = setup_decision_fixture(as_of, "LONG")
    _, short_fix = setup_decision_fixture(as_of, "SHORT")

    candles = make_dummy_candles(
        as_of,
        1,
        base_price=50000.0,
        price_step=200.0,
        high_offset=300.0,
        low_offset=100.0,
    )
    # Candle 0: open=49995.0, high=50300.0, low=49900.0, close=50000.0
    eval_time = as_of + timedelta(hours=1, minutes=5)

    # Test LONG
    long_out = evaluate_horizon_outcome(
        decision=long_fix["decision"],
        horizon="+1h",
        candles=candles,
        evaluation_time_utc=eval_time,
    )
    assert long_out.decision_outcome == "LONG"
    assert long_out.raw_return > 0
    assert long_out.mfe > 0
    assert long_out.mae < 0
    assert long_out.opportunity_return is None

    # Test SHORT
    short_out = evaluate_horizon_outcome(
        decision=short_fix["decision"],
        horizon="+1h",
        candles=candles,
        evaluation_time_utc=eval_time,
    )
    assert short_out.decision_outcome == "SHORT"
    assert short_out.raw_return < 0
    assert short_out.mfe > 0
    assert short_out.mae < 0
    assert short_out.opportunity_return is None


def test_horizon_calculations_1h_4h_24h():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 24, base_price=50000.0, price_step=50.0)
    eval_time = as_of + timedelta(hours=24, minutes=5)

    out_1h = evaluate_horizon_outcome(
        decision=decision, horizon="+1h", candles=candles, evaluation_time_utc=eval_time
    )
    out_4h = evaluate_horizon_outcome(
        decision=decision, horizon="+4h", candles=candles, evaluation_time_utc=eval_time
    )
    out_24h = evaluate_horizon_outcome(
        decision=decision, horizon="+24h", candles=candles, evaluation_time_utc=eval_time
    )

    assert out_1h.status == "evaluated"
    assert out_4h.status == "evaluated"
    assert out_24h.status == "evaluated"

    assert out_1h.data_health.candle_count == 1
    assert out_4h.data_health.candle_count == 4
    assert out_24h.data_health.candle_count == 24

    assert out_1h.horizon_close_utc == as_of + timedelta(hours=1)
    assert out_4h.horizon_close_utc == as_of + timedelta(hours=4)
    assert out_24h.horizon_close_utc == as_of + timedelta(hours=24)


def test_pending_horizon():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    # Evaluation time is only +2h after decision, so +4h and +24h are pending
    eval_time = as_of + timedelta(hours=2)
    candles = make_dummy_candles(as_of, 2)

    out_4h = evaluate_horizon_outcome(
        decision=decision, horizon="+4h", candles=candles, evaluation_time_utc=eval_time
    )
    assert out_4h.status == "pending"
    assert "horizon_not_expired" in out_4h.data_health.missing_reasons
    assert not out_4h.data_health.ready


def test_missing_and_gap_data_results_in_unavailable():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    # 4h horizon expected, but we only supply candles 0 and 2 (missing candle 1 and 3)
    candles_all = make_dummy_candles(as_of, 4)
    candles_gap = [candles_all[0], candles_all[2]]
    eval_time = as_of + timedelta(hours=5)

    out = evaluate_horizon_outcome(
        decision=decision, horizon="+4h", candles=candles_gap, evaluation_time_utc=eval_time
    )
    assert out.status == "unavailable"
    assert not out.data_health.ready
    assert (
        "incomplete_horizon_4h" in out.data_health.missing_reasons
        or "horizon_gap_detected" in out.data_health.missing_reasons
    )


def test_lookahead_and_available_at_protection():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    # Candle available_at is set in the future (after horizon_close)
    candles = make_dummy_candles(as_of, 1, available_lag_hours=5)
    eval_time = as_of + timedelta(hours=2)

    out = evaluate_horizon_outcome(
        decision=decision, horizon="+1h", candles=candles, evaluation_time_utc=eval_time
    )
    assert out.status == "unavailable"
    assert not out.data_health.ready
    assert "missing_horizon_candles" in out.data_health.missing_reasons


def test_idempotent_retry_and_conflict_detection():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 1)
    eval_time = as_of + timedelta(hours=2)

    outcome = evaluate_horizon_outcome(
        decision=decision, horizon="+1h", candles=candles, evaluation_time_utc=eval_time
    )

    # First record returns True
    recorded = ledger.record_outcome(outcome)
    assert recorded is True

    # Exact second record returns False (idempotent)
    recorded_again = ledger.record_outcome(outcome)
    assert recorded_again is False

    # Conflicting outcome for same decision_id and horizon raises ImmutableDecisionError
    conflicting_health = OutcomeDataHealthV1(
        ready=False,
        missing_reasons=["simulated_conflict"],
        candle_count=0,
        expected_candle_count=1,
    )
    dummy_hash = "a" * 64
    tmp_outcome = DecisionOutcomeV1(
        outcome_id=outcome.outcome_id,
        decision_id=decision.decision_id,
        instrument=decision.instrument,
        as_of_utc=as_of,
        horizon="+1h",
        horizon_close_utc=as_of + timedelta(hours=1),
        decision_outcome=decision.outcome,
        status="unavailable",
        data_health=conflicting_health,
        evaluator_version=EVALUATOR_VERSION,
        content_hash=dummy_hash,
    )
    real_hash = outcome_content_hash(tmp_outcome)
    conflicting_outcome = DecisionOutcomeV1(
        outcome_id=outcome.outcome_id,
        decision_id=decision.decision_id,
        instrument=decision.instrument,
        as_of_utc=as_of,
        horizon="+1h",
        horizon_close_utc=as_of + timedelta(hours=1),
        decision_outcome=decision.outcome,
        status="unavailable",
        data_health=conflicting_health,
        evaluator_version=EVALUATOR_VERSION,
        content_hash=real_hash,
    )

    with pytest.raises(ImmutableDecisionError, match="outcome yeniden yazılamaz"):
        ledger.record_outcome(conflicting_outcome)


def test_sqlite_trigger_update_delete_protection():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 1)
    eval_time = as_of + timedelta(hours=2)

    outcome = evaluate_horizon_outcome(
        decision=decision, horizon="+1h", candles=candles, evaluation_time_utc=eval_time
    )
    ledger.record_outcome(outcome)

    # Direct UPDATE attempt on SQLite table should abort via trigger
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="UPDATE yasak"):
        ledger._conn.execute(
            "UPDATE decision_outcomes SET status='unavailable' WHERE outcome_id=?",
            (outcome.outcome_id,),
        )

    # Direct DELETE attempt on SQLite table should abort via trigger
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="DELETE yasak"):
        ledger._conn.execute(
            "DELETE FROM decision_outcomes WHERE outcome_id=?",
            (outcome.outcome_id,),
        )


def test_replay_determinisim():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 4)
    eval_time = as_of + timedelta(hours=5)

    out1 = evaluate_horizon_outcome(
        decision=decision, horizon="+4h", candles=candles, evaluation_time_utc=eval_time
    )
    out2 = evaluate_horizon_outcome(
        decision=decision, horizon="+4h", candles=candles, evaluation_time_utc=eval_time
    )

    assert out1 == out2
    assert out1.content_hash == out2.content_hash


def test_corrupted_outcome_detected_on_read():
    as_of = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    ledger, fix = setup_decision_fixture(as_of, "WAIT")
    decision = fix["decision"]

    candles = make_dummy_candles(as_of, 1)
    eval_time = as_of + timedelta(hours=2)

    outcome = evaluate_horizon_outcome(
        decision=decision, horizon="+1h", candles=candles, evaluation_time_utc=eval_time
    )

    # Directly insert a corrupted row bypassing record_outcome validation
    data_health_payload, outcome_payload, artifact_hash = ledger._outcome_payloads(outcome)

    ledger._conn.execute(
        """
        INSERT INTO decision_outcomes (
            outcome_id, decision_id, symbol, timeframe, as_of_utc,
            horizon, horizon_close_utc, decision_outcome, status,
            reference_price, horizon_close_price, raw_return, net_return,
            mfe, mae, opportunity_return, data_health_ready,
            data_health_payload, candle_digest, evaluator_version,
            outcome_content_hash, artifact_hash, payload, recorded_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            outcome.outcome_id,
            outcome.decision_id,
            outcome.instrument.symbol,
            outcome.instrument.timeframe,
            "2026-08-04T12:00:00Z",
            outcome.horizon,
            "2026-08-04T13:00:00Z",
            outcome.decision_outcome,
            outcome.status,
            outcome.reference_price,
            outcome.horizon_close_price,
            999.0,  # CORRUPTED INDEX COLUMN!
            outcome.net_return,
            outcome.mfe,
            outcome.mae,
            outcome.opportunity_return,
            1 if outcome.data_health.ready else 0,
            data_health_payload,
            outcome.data_health.candle_digest,
            outcome.evaluator_version,
            outcome.content_hash,
            artifact_hash,
            outcome_payload,
            "2026-08-04T13:05:00Z",
        ),
    )

    with pytest.raises(ImmutableDecisionError, match="kolonları payload ile uyuşmuyor"):
        ledger.get_outcome(outcome.outcome_id)
