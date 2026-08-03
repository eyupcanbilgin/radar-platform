"""Uçtan uca boru hattı testleri: webhook olayı → kapılar → defter → outbox → teslimat."""

from datetime import UTC, datetime, timedelta

import pytest

from enricher.ledger import SignalLedger
from enricher.lifecycle import State
from enricher.outbox import Outbox
from enricher.pipeline import SignalEvent, SignalPipeline
from enricher.policy import load_lifecycle

T0 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
ALL_OK = {
    "candle_close": True,
    "price": True,
    "atr": True,
    "regime": True,
    "blackout_calendar": True,
}


class Collector:
    def __init__(self, fail_until: datetime | None = None):
        self.fail_until = fail_until
        self.now = T0
        self.sent: list[str] = []

    def __call__(self, body: str) -> None:
        if self.fail_until and self.now < self.fail_until:
            raise RuntimeError("teslimat yok (simülasyon)")
        self.sent.append(body)


@pytest.fixture
def pipe():
    led, ob = SignalLedger(), Outbox()
    yield SignalPipeline(ledger=led, outbox=ob, lifecycle=load_lifecycle())
    led.close()
    ob.close()


def _event(**over) -> SignalEvent:
    base = dict(
        asset="BTC",
        strategy="S0001",
        direction="LONG",
        candle_close_utc=T0,
        enter_tag="ema_cross_up",
        rationale="EMA20 EMA50'yi yukarı kesti",
        counter_evidence="Hacim 20-bar ortalamasının altında",
        entry_reference=61250.0,
        invalidation=60100.0,
        inputs_available=dict(ALL_OK),
    )
    base.update(over)
    return SignalEvent(**base)


def test_happy_path_end_to_end(pipe):
    res = pipe.handle(_event(), now=T0)
    assert res.state == State.APPROVED and res.queued
    assert res.signal_id == "BTC-S0001-20260803-1200-L-01"

    sender = Collector()
    pipe.deliver(sender, now=T0)
    assert len(sender.sent) == 1
    assert pipe.ledger.state_of(res.signal_id) == State.SIGNAL_SENT
    assert "İnvalidasyon" in sender.sent[0] and "yatırım tavsiyesi değildir" in sender.sent[0]


def test_missing_required_input_blocks_and_sends_nothing(pipe):
    res = pipe.handle(_event(inputs_available={**ALL_OK, "atr": False}), now=T0)
    assert res.state == State.BLOCKED
    assert "ZORUNLU GİRDİ EKSİK" in res.block_reason
    sender = Collector()
    pipe.deliver(sender, now=T0)
    assert sender.sent == []


def test_missing_regime_still_sends_with_flag(pipe):
    res = pipe.handle(_event(inputs_available={**ALL_OK, "regime": False}), now=T0)
    assert res.state == State.APPROVED
    sender = Collector()
    pipe.deliver(sender, now=T0)
    assert "REJİM ÇEVRİMDIŞI" in sender.sent[0]
    assert pipe.ledger.get(res.signal_id)["degraded_flags"] == "regime"


def test_blackout_blocks_new_signal(pipe):
    res = pipe.handle(_event(blackout_reason="FOMC 18:00 penceresi"), now=T0)
    assert res.state == State.BLOCKED and "KARARTMA AKTİF" in res.block_reason
    assert pipe.ledger.history(res.signal_id)[0]["reason_code"].startswith("blackout:")


def test_duplicate_webhook_does_not_duplicate_signal(pipe):
    first = pipe.handle(_event(), now=T0)
    second = pipe.handle(_event(), now=T0 + timedelta(seconds=3))
    assert first.signal_id == second.signal_id
    assert second.queued is False
    sender = Collector()
    pipe.deliver(sender, now=T0)
    assert len(sender.sent) == 1


def test_two_signals_same_candle_get_distinct_ids(pipe):
    a = pipe.handle(_event(), now=T0)
    b = pipe.handle(_event(direction="SHORT"), now=T0)
    assert a.signal_id.endswith("-L-01")
    assert b.signal_id.endswith("-S-02")


def test_exit_flow_uses_invalidation_language(pipe):
    res = pipe.handle(_event(), now=T0)
    sender = Collector()
    pipe.deliver(sender, now=T0)
    pipe.ledger.apply(
        signal_id=res.signal_id,
        target=State.REFERENCE_OPEN,
        reason_code="reference_fill",
        at_utc=T0,
    )
    pipe.handle_exit(
        signal_id=res.signal_id,
        exit_state=State.STOP_EXIT,
        reason_code="atr_stop_touched",
        reference_price=60100.0,
        now=T0 + timedelta(minutes=40),
    )
    pipe.deliver(sender, now=T0 + timedelta(minutes=40))
    assert len(sender.sent) == 2
    assert "SİSTEM İNVALIDASYONU" in sender.sent[1]
    assert "otomatik kapatılmadı" in sender.sent[1]


def test_outage_then_recovery_delivers_exactly_once(pipe):
    """Kesinti boyunca sinyal üretilir, teslim edilemez; düzelince tam bir kez gider."""
    up_at = T0 + timedelta(minutes=10)
    sender = Collector(fail_until=up_at)
    pipe.handle(_event(), now=T0)
    pipe.handle(_event(candle_close_utc=T0 + timedelta(minutes=15)), now=T0 + timedelta(minutes=15))

    now = T0
    while now <= up_at + timedelta(minutes=5):
        sender.now = now
        pipe.deliver(sender, now=now)
        now += timedelta(seconds=30)

    assert len(sender.sent) == 2
    assert len(set(sender.sent)) == 2
    assert pipe.outbox.counts() == {"SENT": 2}
    for row in pipe.ledger.in_state(State.SIGNAL_SENT):
        assert row["state"] == State.SIGNAL_SENT.value
