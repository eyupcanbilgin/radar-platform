"""Referans pozisyon açılış bildirimi — SIGNAL_SENT → REFERENCE_OPEN.

freqtrade dry-run defteri girişi doldurduğunda burası çağrılır. Ayrı bir modül
olmasının nedeni: yaşam döngüsünde bu adım atlanırsa çıkış bildirimleri geçersiz
geçiş üretir (canlı duman testinde yakalanan durum).
"""

from datetime import UTC, datetime

from enricher.ledger import SignalLedger
from enricher.lifecycle import State


def mark_reference_open(
    ledger: SignalLedger,
    *,
    signal_id: str,
    fill_price: float | None = None,
    now: datetime | None = None,
) -> State:
    reason = "reference_fill" if fill_price is None else f"reference_fill@{fill_price:.2f}"
    ledger.apply(
        signal_id=signal_id,
        target=State.REFERENCE_OPEN,
        reason_code=reason,
        at_utc=now or datetime.now(UTC),
    )
    return ledger.state_of(signal_id)
