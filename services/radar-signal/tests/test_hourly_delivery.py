from datetime import datetime, timedelta

import pytest

from decision_engine.decision import build_hourly_decision
from decision_engine.delivery import HOURLY_DECISION_KIND, HourlyDecisionDelivery
from decision_engine.features import build_feature_snapshot
from decision_engine.ledger import DecisionLedger
from enricher.outbox import PENDING, SENT, Outbox
from tests.test_hourly_decision import SIGNAL_COMMIT, T0, candles_ending_at, context_at


def record_wait(ledger: DecisionLedger, *, as_of: datetime = T0):
    feature = build_feature_snapshot(candles_ending_at(as_of), as_of=as_of)
    decision = build_hourly_decision(feature, context_at(as_of), signal_commit=SIGNAL_COMMIT)
    ledger.record(feature=feature, context=context_at(as_of), decision=decision)
    return decision


def test_wait_message_is_first_class_safe_and_deterministic():
    with DecisionLedger() as ledger, Outbox() as outbox:
        decision = record_wait(ledger)
        delivery = HourlyDecisionDelivery(ledger=ledger, outbox=outbox)
        assert delivery.enqueue_decision(decision.decision_id, now=T0) is True
        assert (
            delivery.enqueue_decision(decision.decision_id, now=T0 + timedelta(minutes=1)) is False
        )
        body = outbox.get(signal_id=decision.decision_id, kind=HOURLY_DECISION_KIND)["body"]
        assert "Sonuç: WAIT" in body
        assert "WAIT, yön veya nötr getiri ölçüldüğü anlamına gelmez." in body
        assert "real_orders=false" in body
        assert decision.feature_snapshot_id in body
        assert decision.context_snapshot_id in body


def test_blockers_remain_visible_and_do_not_become_neutral_score():
    with DecisionLedger() as ledger, Outbox() as outbox:
        feature = build_feature_snapshot(candles_ending_at(T0), as_of=T0)
        context = context_at(T0, blocked=True)
        decision = build_hourly_decision(feature, context, signal_commit=SIGNAL_COMMIT)
        ledger.record(feature=feature, context=context, decision=decision)
        HourlyDecisionDelivery(ledger=ledger, outbox=outbox).enqueue_decision(
            decision.decision_id, now=T0
        )
        body = outbox.get(signal_id=decision.decision_id, kind=HOURLY_DECISION_KIND)["body"]
        assert "Sonuç: WAIT" in body
        assert "context:missing_required_layer:derivatives" in body
        assert "nötr getiri ölçüldüğü anlamına gelmez" in body


def test_reconcile_repairs_ledger_outbox_crash_gap_with_bound():
    with DecisionLedger() as ledger, Outbox() as outbox:
        old = record_wait(ledger, as_of=T0)
        recent = record_wait(ledger, as_of=T0 + timedelta(hours=1))
        delivery = HourlyDecisionDelivery(ledger=ledger, outbox=outbox)
        assert delivery.reconcile(limit=1, now=T0) == {"scanned": 1, "enqueued": 1, "existing": 0}
        assert outbox.get(signal_id=recent.decision_id, kind=HOURLY_DECISION_KIND)
        assert outbox.get(signal_id=old.decision_id, kind=HOURLY_DECISION_KIND) is None


def test_telegram_outage_keeps_decision_pending_then_sends_once():
    calls = []

    def down(_body: str):
        raise RuntimeError("telegram down")

    with DecisionLedger() as ledger, Outbox(backoff_seconds=[1]) as outbox:
        decision = record_wait(ledger)
        HourlyDecisionDelivery(ledger=ledger, outbox=outbox).enqueue_decision(
            decision.decision_id, now=T0
        )
        assert outbox.pump(down, now=T0)["failed"] == 1
        assert outbox.counts() == {PENDING: 1}
        assert outbox.pump(calls.append, now=T0 + timedelta(seconds=1))["sent"] == 1
        assert outbox.pump(calls.append, now=T0 + timedelta(minutes=1))["sent"] == 0
        assert len(calls) == 1
        assert outbox.counts() == {SENT: 1}


def test_reconcile_rejects_unbounded_limit():
    with DecisionLedger() as ledger, Outbox() as outbox:
        with pytest.raises(ValueError, match="limit"):
            HourlyDecisionDelivery(ledger=ledger, outbox=outbox).reconcile(limit=0)
