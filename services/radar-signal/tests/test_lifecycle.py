"""State machine + defter testleri (CR-002 P0-4, CLAUDE.md kural 9)."""

from datetime import UTC, datetime, timedelta

import pytest

from enricher.ledger import SignalLedger, make_signal_id
from enricher.lifecycle import (
    EXIT_STATES,
    IllegalTransition,
    State,
    resolve_exit_conflict,
    transition,
)
from enricher.policy import load_lifecycle

T0 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_signal_id_format():
    sid = make_signal_id(asset="BTC", strategy="S0002", candle_close_utc=T0, direction="LONG")
    assert sid == "BTC-S0002-20260803-1200-L-01"
    short = make_signal_id(
        asset="ETH", strategy="S0004a", candle_close_utc=T0, direction="SHORT", seq=2
    )
    assert short == "ETH-S0004a-20260803-1200-S-02"


def test_bad_direction_fails_loud():
    with pytest.raises(ValueError, match="LONG|SHORT"):
        make_signal_id(asset="BTC", strategy="S", candle_close_utc=T0, direction="up")


def test_happy_path_full_lifecycle():
    with SignalLedger() as led:
        sid = make_signal_id(asset="BTC", strategy="S0001", candle_close_utc=T0, direction="LONG")
        led.create(
            signal_id=sid, asset="BTC", strategy="S0001", direction="LONG", candle_close_utc=T0
        )
        assert led.state_of(sid) == State.CANDIDATE
        for target, reason in [
            (State.APPROVED, "gates_passed"),
            (State.SIGNAL_SENT, "outbox_delivered"),
            (State.REFERENCE_OPEN, "reference_fill"),
            (State.STOP_EXIT, "atr_stop_touched"),
            (State.CLOSED, "bookkeeping_done"),
        ]:
            led.apply(signal_id=sid, target=target, reason_code=reason, at_utc=T0)
        assert led.state_of(sid) == State.CLOSED
        assert [h["to_state"] for h in led.history(sid)] == [
            "APPROVED",
            "SIGNAL_SENT",
            "REFERENCE_OPEN",
            "STOP_EXIT",
            "CLOSED",
        ]


def test_state_skipping_is_rejected():
    """CANDIDATE'tan doğrudan REFERENCE_OPEN'a atlamak yasak (kural 9)."""
    with SignalLedger() as led:
        sid = "BTC-S0001-20260803-1200-L-01"
        led.create(
            signal_id=sid, asset="BTC", strategy="S0001", direction="LONG", candle_close_utc=T0
        )
        with pytest.raises(IllegalTransition, match="tanımsız"):
            led.apply(signal_id=sid, target=State.REFERENCE_OPEN, reason_code="x", at_utc=T0)
        assert led.state_of(sid) == State.CANDIDATE  # durum bozulmadı


def test_blocked_signal_cannot_be_sent():
    with SignalLedger() as led:
        sid = "BTC-S0001-20260803-1200-L-01"
        led.create(
            signal_id=sid, asset="BTC", strategy="S0001", direction="LONG", candle_close_utc=T0
        )
        led.apply(signal_id=sid, target=State.BLOCKED, reason_code="blackout_fomc", at_utc=T0)
        with pytest.raises(IllegalTransition):
            led.apply(signal_id=sid, target=State.SIGNAL_SENT, reason_code="x", at_utc=T0)


def test_transition_is_idempotent():
    with SignalLedger() as led:
        sid = "BTC-S0001-20260803-1200-L-01"
        led.create(
            signal_id=sid, asset="BTC", strategy="S0001", direction="LONG", candle_close_utc=T0
        )
        assert led.apply(signal_id=sid, target=State.APPROVED, reason_code="ok", at_utc=T0)
        assert led.apply(signal_id=sid, target=State.APPROVED, reason_code="ok", at_utc=T0) is None
        assert len(led.history(sid)) == 1


def test_create_is_idempotent():
    with SignalLedger() as led:
        sid = "BTC-S0001-20260803-1200-L-01"
        kw = dict(
            signal_id=sid, asset="BTC", strategy="S0001", direction="LONG", candle_close_utc=T0
        )
        assert led.create(**kw) is True
        assert led.create(**kw) is False


def test_reason_code_is_mandatory():
    with pytest.raises(ValueError, match="reason_code"):
        transition(
            signal_id="x", current=State.CANDIDATE, target=State.APPROVED, reason_code="", at_utc=T0
        )


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        transition(
            signal_id="x",
            current=State.CANDIDATE,
            target=State.APPROVED,
            reason_code="ok",
            at_utc=datetime(2026, 8, 3, 12, 0),
        )


def test_stop_beats_candle_close_exit():
    """P0-4: mum kapanışı çıkışı ile stop aynı anda tetiklenirse STOP kazanır."""
    precedence = load_lifecycle()["exit_precedence"]
    winner = resolve_exit_conflict([State.STRATEGY_EXIT, State.STOP_EXIT], precedence)
    assert winner == State.STOP_EXIT


def test_roi_beats_strategy_but_loses_to_stop():
    precedence = load_lifecycle()["exit_precedence"]
    roi_vs_strategy = resolve_exit_conflict([State.STRATEGY_EXIT, State.ROI_EXIT], precedence)
    assert roi_vs_strategy == State.ROI_EXIT
    stop_vs_roi = resolve_exit_conflict([State.ROI_EXIT, State.STOP_EXIT], precedence)
    assert stop_vs_roi == State.STOP_EXIT


def test_every_exit_state_is_in_precedence_config():
    """Config eksik kalırsa çıkış çakışması sessizce yanlış çözülürdü."""
    precedence = load_lifecycle()["exit_precedence"]
    assert {s.value for s in EXIT_STATES} == set(precedence)


def test_unknown_exit_in_conflict_fails_loud():
    with pytest.raises(ValueError, match="tanımsız çıkış"):
        resolve_exit_conflict([State.STOP_EXIT], ["ROI_EXIT"])


def test_next_seq_increments_within_same_candle():
    with SignalLedger() as led:
        kw = dict(asset="BTC", strategy="S0001", candle_close_utc=T0)
        assert led.next_seq(**kw) == 1
        led.create(
            signal_id=make_signal_id(**kw, direction="LONG"),
            direction="LONG",
            **kw,
        )
        assert led.next_seq(**kw) == 2
        next_candle = T0 + timedelta(minutes=15)
        assert led.next_seq(asset="BTC", strategy="S0001", candle_close_utc=next_candle) == 1
