import hashlib
import json
import math
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from decision_engine.decision import (
    DirectionalSetup,
    build_hourly_decision,
    verify_decision_card,
)
from decision_engine.features import (
    LOOKBACK_BARS,
    Candle1h,
    build_feature_snapshot,
    verify_feature_snapshot,
)
from decision_engine.ledger import DecisionLedger, ImmutableDecisionError
from decision_engine.service import HourlyDecisionService
from enricher.decision_context import DecisionContextV1

T0 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
SIGNAL_COMMIT = "1234567890ab"
PLATFORM_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_FIXTURE = (
    PLATFORM_ROOT / "contracts" / "decision-context" / "v1" / "examples" / "btc-1h-context.json"
)


def candles_ending_at(end: datetime, count: int = LOOKBACK_BARS) -> list[Candle1h]:
    first_close = end - timedelta(hours=count - 1)
    candles = []
    previous_close = 50_000.0
    for index in range(count):
        close_time = first_close + timedelta(hours=index)
        close = 50_000.0 + index * 11.0 + math.sin(index / 7.0) * 35.0
        open_price = previous_close
        candles.append(
            Candle1h(
                open_time_utc=close_time - timedelta(hours=1),
                close_time_utc=close_time,
                available_at_utc=close_time,
                open=open_price,
                high=max(open_price, close) + 25.0,
                low=min(open_price, close) - 25.0,
                close=close,
                volume=1_000.0 + index * 3.0,
            )
        )
        previous_close = close
    return candles


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


def setup(feature, direction: str = "LONG") -> DirectionalSetup:
    return DirectionalSetup(
        setup_id="SETUP-S0001-ema-control",
        hypothesis_id="S-0001",
        rule_version="control-v1",
        as_of_utc=feature.as_of_utc,
        feature_snapshot_id=feature.snapshot_id,
        feature_content_hash=feature.content_hash,
        direction=direction,
        rationale="Kontrol setup arayüzü tetiklendi",
        counter_evidence="Bu fixture yalnız orchestration testidir",
    )


def test_feature_snapshot_is_ready_versioned_and_hash_verified():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    assert feature.ready is True
    assert feature.source_bars == LOOKBACK_BARS
    assert feature.schema_version == "feature-snapshot/v1"
    assert feature.snapshot_id.startswith("FS-")
    assert feature.features.atr14_sma_pct is not None
    assert feature.features.realized_vol_24h is not None
    verify_feature_snapshot(feature)


def test_feature_snapshot_is_bit_identical_across_replays():
    candles = candles_ending_at(T0)
    payloads = {
        build_feature_snapshot(list(reversed(candles)), as_of=T0).model_dump_json()
        for _ in range(100)
    }
    assert len(payloads) == 1


def test_future_candle_cannot_change_feature_snapshot():
    candles = candles_ending_at(T0)
    base = build_feature_snapshot(candles, as_of=T0)
    future = Candle1h(
        open_time_utc=T0,
        close_time_utc=T0 + timedelta(hours=1),
        available_at_utc=T0 + timedelta(hours=1),
        open=52_000.0,
        high=100_000.0,
        low=1.0,
        close=99_000.0,
        volume=9_000_000.0,
    )
    with_future = build_feature_snapshot([*candles, future], as_of=T0)
    assert with_future == base


def test_unavailable_decision_candle_yields_explicit_not_ready_snapshot():
    candles = candles_ending_at(T0)
    candles[-1] = candles[-1].model_copy(update={"available_at_utc": T0 + timedelta(seconds=1)})
    feature = build_feature_snapshot(candles, as_of=T0)
    assert feature.ready is False
    assert "decision_candle" in feature.missing_features
    assert f"history_{LOOKBACK_BARS}" in feature.missing_features


def test_duplicate_candle_close_fails_loud():
    candles = candles_ending_at(T0)
    with pytest.raises(ValueError, match="birden fazla mum"):
        build_feature_snapshot([*candles, candles[-1]], as_of=T0)


def test_tampered_feature_snapshot_is_rejected():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    tampered = feature.model_copy(update={"content_hash": "0" * 64})
    with pytest.raises(ValueError, match="content_hash uyuşmuyor"):
        verify_feature_snapshot(tampered)


def test_ready_hour_without_setup_records_first_class_wait():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    card = build_hourly_decision(feature, context_at(T0), signal_commit=SIGNAL_COMMIT)
    assert card.outcome == "WAIT"
    assert card.reasons == ["no_directional_setup"]
    assert card.blockers == []
    assert card.real_orders is False
    verify_decision_card(card)


def test_closed_context_gate_suppresses_candidate_to_wait():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    card = build_hourly_decision(
        feature,
        context_at(T0, blocked=True),
        setup=setup(feature),
        signal_commit=SIGNAL_COMMIT,
    )
    assert card.outcome == "WAIT"
    assert card.candidate is not None
    assert card.blockers == ["context:missing_required_layer:derivatives"]


def test_open_gates_can_carry_strategy_neutral_directional_candidate():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    card = build_hourly_decision(
        feature,
        context_at(T0),
        setup=setup(feature, "SHORT"),
        signal_commit=SIGNAL_COMMIT,
    )
    assert card.outcome == "SHORT"
    assert card.candidate.direction == "SHORT"
    assert card.blockers == []


def test_setup_from_another_feature_hour_is_rejected():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    next_hour = T0 + timedelta(hours=1)
    future_feature = build_feature_snapshot(candles_ending_at(next_hour), as_of=next_hour)
    with pytest.raises(ValueError, match="setup ve feature aynı as_of_utc"):
        build_hourly_decision(
            feature,
            context_at(T0),
            setup=setup(future_feature),
            signal_commit=SIGNAL_COMMIT,
        )


def test_decision_card_is_bit_identical_across_replays():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    context = context_at(T0)
    cards = {
        build_hourly_decision(feature, context, signal_commit=SIGNAL_COMMIT).model_dump_json()
        for _ in range(100)
    }
    assert len(cards) == 1


def test_hourly_service_records_exact_retry_idempotently():
    with DecisionLedger() as ledger:
        service = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT)
        kwargs = {"candles": candles_ending_at(T0), "context": context_at(T0)}
        first = service.evaluate_and_record(**kwargs, recorded_at_utc=T0)
        second = service.evaluate_and_record(**kwargs, recorded_at_utc=T0 + timedelta(minutes=1))
        assert first.created is True
        assert second.created is False
        assert first.decision == second.decision
        assert ledger.count() == 1


def test_context_wall_clock_change_is_semantically_idempotent():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    first_context = context_at(T0)
    payload = first_context.model_dump(mode="json")
    payload["snapshot"]["computed_at_utc"] = "2026-08-03T12:00:45Z"
    recomputed_context = DecisionContextV1.model_validate(payload)
    first_card = build_hourly_decision(feature, first_context, signal_commit=SIGNAL_COMMIT)
    second_card = build_hourly_decision(feature, recomputed_context, signal_commit=SIGNAL_COMMIT)
    assert first_card == second_card
    with DecisionLedger() as ledger:
        assert ledger.record(
            feature=feature,
            context=first_context,
            decision=first_card,
            recorded_at_utc=T0,
        )
        assert not ledger.record(
            feature=feature,
            context=recomputed_context,
            decision=second_card,
            recorded_at_utc=T0 + timedelta(minutes=1),
        )
        assert ledger.count() == 1


def test_missing_context_still_records_hour_as_blocked_wait():
    with DecisionLedger() as ledger:
        service = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT)
        result = service.evaluate_and_record(
            candles=candles_ending_at(T0),
            context=None,
            as_of_utc=T0,
            recorded_at_utc=T0,
        )
        assert result.decision.outcome == "WAIT"
        assert result.decision.blockers == ["context:missing"]
        row = ledger.get(result.decision.decision_id)
        assert row["context_payload"] is None
        assert ledger.count() == 1


def test_same_hour_cannot_be_rewritten_with_different_decision():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    context = context_at(T0)
    wait = build_hourly_decision(feature, context, signal_commit=SIGNAL_COMMIT)
    directional = build_hourly_decision(
        feature, context, setup=setup(feature), signal_commit=SIGNAL_COMMIT
    )
    with DecisionLedger() as ledger:
        assert ledger.record(feature=feature, context=context, decision=wait, recorded_at_utc=T0)
        with pytest.raises(ImmutableDecisionError, match="yeniden yazılamaz"):
            ledger.record(
                feature=feature,
                context=context,
                decision=directional,
                recorded_at_utc=T0,
            )
        assert ledger.count() == 1
        assert ledger.feature_count() == 1


def test_ledger_rejects_directional_card_when_supplied_context_gate_is_closed():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    directional = build_hourly_decision(
        feature,
        context_at(T0),
        setup=setup(feature),
        signal_commit=SIGNAL_COMMIT,
    )
    with DecisionLedger() as ledger:
        with pytest.raises(ValueError, match="girdilerinden yeniden üretilemiyor"):
            ledger.record(
                feature=feature,
                context=context_at(T0, blocked=True),
                decision=directional,
                recorded_at_utc=T0,
            )
        assert ledger.feature_count() == 0
        assert ledger.count() == 0


def test_ledger_persists_complete_replay_bundle(tmp_path: Path):
    path = tmp_path / "decisions.sqlite"
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    context = context_at(T0)
    card = build_hourly_decision(feature, context, signal_commit=SIGNAL_COMMIT)
    with DecisionLedger(path) as ledger:
        ledger.record(feature=feature, context=context, decision=card, recorded_at_utc=T0)
    with DecisionLedger(path) as ledger:
        row = ledger.get(card.decision_id)
        assert row["feature_payload"] == feature.model_dump(mode="json")
        assert row["context_payload"] == context.model_dump(mode="json")
        assert row["decision_payload"] == card.model_dump(mode="json")
        assert len(row["artifact_hash"]) == 64


def test_feature_conflict_rolls_back_without_orphan_snapshot():
    context = context_at(T0)
    first_feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    changed_candles = candles_ending_at(T0)
    last = changed_candles[-1]
    changed_candles[-1] = last.model_copy(
        update={"close": last.close + 5.0, "high": last.high + 5.0}
    )
    second_feature = build_feature_snapshot(changed_candles, as_of=T0)
    first_card = build_hourly_decision(first_feature, context, signal_commit=SIGNAL_COMMIT)
    second_card = build_hourly_decision(second_feature, context, signal_commit=SIGNAL_COMMIT)
    with DecisionLedger() as ledger:
        ledger.record(
            feature=first_feature,
            context=context,
            decision=first_card,
            recorded_at_utc=T0,
        )
        with pytest.raises(ImmutableDecisionError, match="feature snapshot yeniden yazılamaz"):
            ledger.record(
                feature=second_feature,
                context=context,
                decision=second_card,
                recorded_at_utc=T0,
            )
        assert ledger.feature_count() == 1
        assert ledger.count() == 1


def test_sqlite_triggers_block_update_and_delete(tmp_path: Path):
    path = tmp_path / "append-only.sqlite"
    with DecisionLedger(path) as ledger:
        service = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT)
        service.evaluate_and_record(
            candles=candles_ending_at(T0),
            context=context_at(T0),
            recorded_at_utc=T0,
        )
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE hourly_decisions SET outcome='LONG'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM feature_snapshots")


def test_sqlite_trigger_blocks_insert_or_replace(tmp_path: Path):
    path = tmp_path / "replace.sqlite"
    with DecisionLedger(path) as ledger:
        service = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT)
        service.evaluate_and_record(
            candles=candles_ending_at(T0),
            context=context_at(T0),
            recorded_at_utc=T0,
        )
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                """
                INSERT OR REPLACE INTO hourly_decisions (
                    decision_id, symbol, timeframe, as_of_utc, outcome,
                    feature_snapshot_id, context_snapshot_id, feature_content_hash,
                    context_content_hash, decision_content_hash, artifact_hash,
                    context_payload, decision_payload, recorded_at_utc
                )
                SELECT decision_id, symbol, timeframe, as_of_utc, 'LONG',
                       feature_snapshot_id, context_snapshot_id, feature_content_hash,
                       context_content_hash, decision_content_hash, artifact_hash,
                       context_payload, decision_payload, recorded_at_utc
                FROM hourly_decisions
                """
            )


def test_read_rejects_stored_columns_that_disagree_with_payload(tmp_path: Path):
    path = tmp_path / "tampered.sqlite"
    with DecisionLedger(path) as ledger:
        result = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT).evaluate_and_record(
            candles=candles_ending_at(T0),
            context=context_at(T0),
            recorded_at_utc=T0,
        )
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER hourly_decisions_no_update")
        connection.execute("UPDATE hourly_decisions SET outcome='LONG'")
        connection.commit()
    with DecisionLedger(path) as ledger:
        with pytest.raises(ImmutableDecisionError, match="kolonları payload ile uyuşmuyor"):
            ledger.get(result.decision.decision_id)


def test_code_version_changes_content_not_natural_hourly_id():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    context = context_at(T0)
    first = build_hourly_decision(feature, context, signal_commit=SIGNAL_COMMIT)
    second = build_hourly_decision(feature, context, signal_commit="abcdef012345")
    assert first.decision_id == second.decision_id
    assert first.content_hash != second.content_hash


def test_every_processed_hour_gets_a_wait_ledger_row():
    master = candles_ending_at(T0 + timedelta(hours=2), LOOKBACK_BARS + 2)
    with DecisionLedger() as ledger:
        service = HourlyDecisionService(ledger, signal_commit=SIGNAL_COMMIT)
        for offset in range(3):
            as_of = T0 + timedelta(hours=offset)
            result = service.evaluate_and_record(
                candles=master,
                context=context_at(as_of),
                recorded_at_utc=as_of,
            )
            assert result.decision.outcome == "WAIT"
            assert result.created is True
        assert ledger.count() == 3
        assert ledger.outcome_counts() == {"WAIT": 3}


def test_mismatched_context_hour_is_rejected_before_ledger_write():
    feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
    with pytest.raises(ValueError, match="aynı as_of_utc"):
        build_hourly_decision(
            feature,
            context_at(T0 + timedelta(hours=1)),
            signal_commit=SIGNAL_COMMIT,
        )


def test_modified_candle_changes_snapshot_and_decision_identity():
    candles = candles_ending_at(T0)
    first_feature = build_feature_snapshot(candles, as_of=T0)
    changed = deepcopy(candles)
    last = changed[-1]
    changed[-1] = last.model_copy(update={"close": last.close + 5.0, "high": last.high + 5.0})
    second_feature = build_feature_snapshot(changed, as_of=T0)
    assert second_feature.snapshot_id != first_feature.snapshot_id
    first_card = build_hourly_decision(first_feature, context_at(T0), signal_commit=SIGNAL_COMMIT)
    second_card = build_hourly_decision(second_feature, context_at(T0), signal_commit=SIGNAL_COMMIT)
    assert second_card.decision_id == first_card.decision_id
    assert second_card.content_hash != first_card.content_hash
