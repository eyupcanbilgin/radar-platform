"""Outbox testleri — KABUL TESTİ: 10 dk Telegram kesintisi → kayıp yok, çift yok."""

from datetime import UTC, datetime, timedelta

import pytest

from enricher.outbox import DEAD, PENDING, SENT, Outbox

T0 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


class FlakySender:
    """Belirli bir ana kadar hata fırlatan sahte teslimatçı (kesinti simülasyonu)."""

    def __init__(self, up_at: datetime):
        self.up_at = up_at
        self.now = T0
        self.delivered: list[str] = []
        self.attempts = 0

    def __call__(self, body: str) -> None:
        self.attempts += 1
        if self.now < self.up_at:
            raise RuntimeError("Telegram erişilemiyor (simülasyon)")
        self.delivered.append(body)


def test_enqueue_is_idempotent():
    with Outbox() as ob:
        assert ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0) is True
        assert ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0) is False
        assert ob.counts() == {PENDING: 1}


def test_same_idempotency_key_with_different_body_fails_loud():
    with Outbox() as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0)
        with pytest.raises(ValueError, match="farklı gövde"):
            ob.enqueue(signal_id="S1", kind="signal", body="b", now=T0)
        assert ob.get(signal_id="S1", kind="signal")["body"] == "a"


def test_same_signal_different_kinds_are_separate():
    with Outbox() as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="giriş", now=T0)
        ob.enqueue(signal_id="S1", kind="exit", body="kapanış", now=T0)
        assert ob.counts() == {PENDING: 2}


def test_sent_message_never_resent():
    sender = FlakySender(up_at=T0)
    sender.now = T0
    with Outbox() as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0)
        assert ob.pump(sender, now=T0) == {"sent": 1, "failed": 0, "dead": 0}
        for i in range(5):  # pompa tekrar tekrar dönse de aynı mesaj bir daha gitmez
            ob.pump(sender, now=T0 + timedelta(minutes=i + 1))
        assert len(sender.delivered) == 1
        assert ob.counts() == {SENT: 1}


def test_ten_minute_outage_no_loss_no_duplicates():
    """KABUL TESTİ (CR-002 P0-4): 10 dk kesinti boyunca 4 sinyal kuyruğa girer."""
    outage_end = T0 + timedelta(minutes=10)
    sender = FlakySender(up_at=outage_end)

    with Outbox(backoff_seconds=[30, 60, 120], max_attempts=50) as ob:
        # Kesinti boyunca her 2,5 dakikada bir sinyal üretiliyor; pompa sürekli dönüyor
        now = T0
        enqueued = 0
        while now <= outage_end + timedelta(minutes=5):
            if now < outage_end and (now - T0).total_seconds() % 150 == 0:
                enqueued += 1
                ob.enqueue(
                    signal_id=f"BTC-S0001-{enqueued:02d}",
                    kind="signal",
                    body=f"sinyal {enqueued}",
                    now=now,
                )
            sender.now = now
            ob.pump(sender, now=now)
            now += timedelta(seconds=30)

        assert enqueued == 4, "kesinti sırasında 4 sinyal üretilmeliydi"
        # KAYIP YOK: hepsi teslim edildi
        assert ob.counts() == {SENT: 4}
        # ÇİFT YOK: 4 sinyal, 4 teslim
        assert len(sender.delivered) == 4
        assert len({d.split("\n")[0] for d in sender.delivered}) == 4
        # Kesinti sırasında denemeler yapıldı ama hiçbiri teslim sayılmadı
        assert sender.attempts > 4


def test_late_delivery_note_added_after_outage():
    outage_end = T0 + timedelta(minutes=10)
    sender = FlakySender(up_at=outage_end)
    with Outbox(backoff_seconds=[60], late_delivery_after_minutes=5) as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="gövde", now=T0)
        now = T0
        while now <= outage_end + timedelta(minutes=1):
            sender.now = now
            ob.pump(sender, now=now)
            now += timedelta(minutes=1)
    assert len(sender.delivered) == 1
    assert "[GEÇ TESLİM]" in sender.delivered[0]
    assert "dk gecikmeyle" in sender.delivered[0]


def test_fresh_delivery_has_no_late_note():
    sender = FlakySender(up_at=T0)
    with Outbox(late_delivery_after_minutes=5) as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="gövde", now=T0)
        ob.pump(sender, now=T0 + timedelta(minutes=1))
    assert "[GEÇ TESLİM]" not in sender.delivered[0]


def test_backoff_prevents_hammering():
    """Başarısız denemeden hemen sonra tekrar denenmez (backoff)."""
    sender = FlakySender(up_at=T0 + timedelta(hours=1))
    with Outbox(backoff_seconds=[60]) as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0)
        sender.now = T0
        ob.pump(sender, now=T0)
        assert sender.attempts == 1
        ob.pump(sender, now=T0 + timedelta(seconds=30))  # henüz sırası gelmedi
        assert sender.attempts == 1
        ob.pump(sender, now=T0 + timedelta(seconds=61))
        assert sender.attempts == 2


def test_dead_letter_after_max_attempts():
    sender = FlakySender(up_at=T0 + timedelta(days=365))
    with Outbox(backoff_seconds=[1], max_attempts=3) as ob:
        ob.enqueue(signal_id="S1", kind="signal", body="a", now=T0)
        now = T0
        for _ in range(5):
            sender.now = now
            ob.pump(sender, now=now)
            now += timedelta(seconds=2)
        assert ob.counts() == {DEAD: 1}
        row = ob.get(signal_id="S1", kind="signal")
        assert row["attempts"] == 3
        assert "erişilemiyor" in row["last_error"]


def test_naive_datetime_rejected():
    with Outbox() as ob:
        with pytest.raises(ValueError, match="naive"):
            ob.enqueue(signal_id="S1", kind="signal", body="a", now=datetime(2026, 8, 3))
