"""Uçtan uca sinyal boru hattı: webhook → kapılar → defter → outbox → teslimat.

Bu modül HTTP bilmez (o `app.py`'nin işi) ve sinyal üretmez (o stratejinin işi).
Yaptığı tek şey: gelen sinyal olayını politikadan geçirip yaşam döngüsüne oturtmak.

Akış:
    CANDIDATE  → (zorunlu girdi eksik) → BLOCKED
               → (karartma penceresi)   → BLOCKED
               → APPROVED → outbox'a yaz → teslim edilince SIGNAL_SENT
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from enricher.formatting import build_exit_message, build_signal_message
from enricher.ledger import SignalLedger, make_signal_id
from enricher.lifecycle import State
from enricher.outbox import Outbox
from enricher.policy import evaluate_inputs

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    """freqtrade webhook'undan gelen ham sinyal olayı."""

    asset: str
    strategy: str
    direction: str  # LONG | SHORT
    candle_close_utc: datetime
    enter_tag: str
    rationale: str
    counter_evidence: str
    entry_reference: float | None
    invalidation: float | None
    timeframe: str = "15m"
    snapshot_id: str | None = None
    regime_line: str = "REJİM ÇEVRİMDIŞI — değerlendirilemedi"
    data_health: str = "bilinmiyor"
    inputs_available: dict[str, bool] | None = None
    blackout_reason: str | None = None


@dataclass
class Handled:
    signal_id: str
    state: State
    queued: bool
    block_reason: str | None = None
    degraded_flags: list[str] | None = None


class SignalPipeline:
    def __init__(self, *, ledger: SignalLedger, outbox: Outbox, lifecycle: dict):
        self.ledger = ledger
        self.outbox = outbox
        self.lifecycle = lifecycle

    def handle(self, event: SignalEvent, *, now: datetime | None = None) -> Handled:
        now = now or datetime.now(UTC)
        # Webhook'un olay kimliği yok: aynı sinyalin tekrarı doğal anahtarla tanınır,
        # yoksa yeni sıra numarası alınır (bkz. SignalLedger.find_existing).
        existing = self.ledger.find_existing(
            asset=event.asset,
            strategy=event.strategy,
            candle_close_utc=event.candle_close_utc,
            direction=event.direction,
            enter_tag=event.enter_tag,
        )
        if existing:
            logger.info("yinelenen sinyal olayı, durum korunuyor: %s", existing["signal_id"])
            return Handled(
                signal_id=existing["signal_id"],
                state=State(existing["state"]),
                queued=False,
            )

        seq = self.ledger.next_seq(
            asset=event.asset, strategy=event.strategy, candle_close_utc=event.candle_close_utc
        )
        signal_id = make_signal_id(
            asset=event.asset,
            strategy=event.strategy,
            candle_close_utc=event.candle_close_utc,
            direction=event.direction,
            seq=seq,
        )
        gate = evaluate_inputs(event.inputs_available or {}, self.lifecycle)
        window = int(self.lifecycle["validity"]["window_minutes"])
        deviation = float(self.lifecycle["validity"]["max_entry_deviation_pct"])
        valid_until = event.candle_close_utc + timedelta(minutes=window)

        created = self.ledger.create(
            signal_id=signal_id,
            asset=event.asset,
            strategy=event.strategy,
            direction=event.direction,
            candle_close_utc=event.candle_close_utc,
            entry_reference=event.entry_reference,
            invalidation=event.invalidation,
            valid_until_utc=valid_until,
            snapshot_id=event.snapshot_id,
            enter_tag=event.enter_tag,
            degraded_flags=gate.degraded_inputs,
            created_at_utc=now,
        )
        if not created:  # yarış durumu emniyeti: kimlik zaten deftere yazılmış
            return Handled(signal_id=signal_id, state=self.ledger.state_of(signal_id), queued=False)

        if not gate.approved:
            self.ledger.apply(
                signal_id=signal_id,
                target=State.BLOCKED,
                reason_code="required_input_missing",
                at_utc=now,
            )
            logger.info("BLOCK %s: %s", signal_id, gate.block_reason)
            return Handled(
                signal_id=signal_id,
                state=State.BLOCKED,
                queued=False,
                block_reason=gate.block_reason,
            )

        if event.blackout_reason:
            self.ledger.apply(
                signal_id=signal_id,
                target=State.BLOCKED,
                reason_code=f"blackout:{event.blackout_reason}",
                at_utc=now,
            )
            return Handled(
                signal_id=signal_id,
                state=State.BLOCKED,
                queued=False,
                block_reason=f"KARARTMA AKTİF — {event.blackout_reason}",
            )

        self.ledger.apply(
            signal_id=signal_id, target=State.APPROVED, reason_code="gates_passed", at_utc=now
        )
        body = build_signal_message(
            signal_id=signal_id,
            asset=event.asset,
            direction=event.direction,
            timeframe=event.timeframe,
            candle_close_utc=event.candle_close_utc.strftime("%Y-%m-%d %H:%M"),
            strategy=event.strategy,
            enter_tag=event.enter_tag,
            rationale=event.rationale,
            counter_evidence=event.counter_evidence,
            entry_reference=event.entry_reference,
            invalidation=event.invalidation,
            valid_until_utc=valid_until.strftime("%Y-%m-%d %H:%M"),
            max_entry_deviation_pct=deviation,
            regime_line=event.regime_line,
            data_health=event.data_health,
            degraded_flags=gate.degraded_flags,
        )
        queued = self.outbox.enqueue(signal_id=signal_id, kind="signal", body=body, now=now)
        return Handled(
            signal_id=signal_id,
            state=State.APPROVED,
            queued=queued,
            degraded_flags=gate.degraded_flags,
        )

    def handle_exit(
        self,
        *,
        signal_id: str,
        exit_state: State,
        reason_code: str,
        reference_price: float | None,
        now: datetime | None = None,
    ) -> Handled:
        now = now or datetime.now(UTC)
        row = self.ledger.get(signal_id)
        if row is None:
            raise KeyError(f"bilinmeyen sinyal: {signal_id}")
        self.ledger.apply(
            signal_id=signal_id, target=exit_state, reason_code=reason_code, at_utc=now
        )
        body = build_exit_message(
            signal_id=signal_id,
            asset=row["asset"],
            exit_state=exit_state.value,
            reason=reason_code,
            reference_price=reference_price,
        )
        queued = self.outbox.enqueue(signal_id=signal_id, kind="exit", body=body, now=now)
        return Handled(signal_id=signal_id, state=exit_state, queued=queued)

    def deliver(self, sender, *, now: datetime | None = None) -> dict:
        """Outbox'ı pompala; teslim edilen sinyalleri SIGNAL_SENT'e taşı."""
        now = now or datetime.now(UTC)
        stats = self.outbox.pump(sender, now=now)
        for row in self.ledger.in_state(State.APPROVED):
            msg = self.outbox.get(signal_id=row["signal_id"], kind="signal")
            if msg and msg["state"] == "SENT":
                self.ledger.apply(
                    signal_id=row["signal_id"],
                    target=State.SIGNAL_SENT,
                    reason_code="outbox_delivered",
                    at_utc=now,
                )
        return stats
