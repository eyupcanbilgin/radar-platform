"""Sinyal yaşam döngüsü state machine — CR-002 P0-4 (CLAUDE.md kural 9).

Durum atlaması ve elle durum yazımı YASAKTIR: tek geçiş kapısı `LifecycleMachine.transition`.
Geçişler idempotent (aynı geçiş iki kez → tek kayıt), timestamp'li ve sebep kodludur.

Çıkış çakışması: aynı anda birden çok çıkış tetiklenirse öncelik `config/lifecycle.yaml`
→ `exit_precedence` listesinden gelir (koda gömülmez). Varsayılan sıralamada STOP_EXIT
en öndedir: "fikrim değişti mum bekler, canım yanıyor beklemez".
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class State(StrEnum):
    CANDIDATE = "CANDIDATE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    APPROVED = "APPROVED"
    SIGNAL_SENT = "SIGNAL_SENT"
    REFERENCE_OPEN = "REFERENCE_OPEN"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    STOP_EXIT = "STOP_EXIT"
    ROI_EXIT = "ROI_EXIT"
    TIME_EXIT = "TIME_EXIT"
    INVALIDATED = "INVALIDATED"
    DATA_FAILURE_EXIT = "DATA_FAILURE_EXIT"
    CLOSED = "CLOSED"


EXIT_STATES = frozenset(
    {
        State.STRATEGY_EXIT,
        State.STOP_EXIT,
        State.ROI_EXIT,
        State.TIME_EXIT,
        State.INVALIDATED,
        State.DATA_FAILURE_EXIT,
    }
)

TERMINAL = State.CLOSED

ALLOWED: dict[State, frozenset[State]] = {
    State.CANDIDATE: frozenset({State.BLOCKED, State.EXPIRED, State.APPROVED}),
    State.APPROVED: frozenset({State.SIGNAL_SENT, State.EXPIRED}),
    State.SIGNAL_SENT: frozenset({State.REFERENCE_OPEN, State.EXPIRED}),
    State.REFERENCE_OPEN: EXIT_STATES,
    State.BLOCKED: frozenset({State.CLOSED}),
    State.EXPIRED: frozenset({State.CLOSED}),
    **{s: frozenset({State.CLOSED}) for s in EXIT_STATES},
    State.CLOSED: frozenset(),
}


class IllegalTransition(Exception):
    """Durum atlaması ya da kapalı geçiş denemesi (kural 9 ihlali)."""


@dataclass(frozen=True)
class Transition:
    signal_id: str
    from_state: State
    to_state: State
    reason_code: str
    at_utc: datetime


def can_transition(src: State, dst: State) -> bool:
    return dst in ALLOWED[src]


def transition(
    *, signal_id: str, current: State, target: State, reason_code: str, at_utc: datetime
) -> Transition | None:
    """Geçişi doğrula ve üret. Aynı duruma tekrar geçiş → None (idempotent, hata değil)."""
    if not reason_code:
        raise ValueError("reason_code zorunlu — sebepsiz durum değişikliği yasak")
    if at_utc.tzinfo is None:
        raise ValueError("at_utc timezone-aware olmalı (UTC)")
    if current == target:
        return None
    if not can_transition(current, target):
        raise IllegalTransition(
            f"{signal_id}: {current.value} → {target.value} geçişi tanımsız; "
            f"izinli hedefler: {sorted(s.value for s in ALLOWED[current])}"
        )
    return Transition(
        signal_id=signal_id,
        from_state=current,
        to_state=target,
        reason_code=reason_code,
        at_utc=at_utc,
    )


def resolve_exit_conflict(triggered: list[State], precedence: list[str]) -> State:
    """Aynı anda tetiklenen çıkışlardan hangisinin geçerli sayılacağını belirler.

    Önceliği config verir; koda gömülü sıra yoktur. Listede olmayan bir çıkış
    tetiklenirse fail-loud (sessizce en sona atmak, kaydı sessizce bozardı).
    """
    if not triggered:
        raise ValueError("tetiklenen çıkış yok")
    unknown = [s.value for s in triggered if s.value not in precedence]
    if unknown:
        raise ValueError(
            f"exit_precedence'ta tanımsız çıkış: {unknown}; config/lifecycle.yaml güncellenmeli"
        )
    if any(s not in EXIT_STATES for s in triggered):
        raise ValueError(f"çıkış olmayan durum verildi: {[s.value for s in triggered]}")
    return min(triggered, key=lambda s: precedence.index(s.value))
