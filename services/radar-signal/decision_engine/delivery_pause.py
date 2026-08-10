"""Operator kill-switch: stop delivery immediately, without losing anything.

Until now the only way to stop the runtime from sending was to kill the pump daemon.  That
is a bad tool for the job: it also stops retry of already-queued messages, it leaves no
record of *why* delivery stopped, and it needs a terminal at the exact moment something is
going wrong.

This is the plan's `manuel pause kill-switch` (Faz 3).  It becomes load-bearing the moment
the fragility warning gate opens (ADR-0048): if a card ever misbehaves, the operator needs a
way to stop delivery in one step and think afterwards.

Three properties make it a safety device rather than a feature flag:

- **Pause holds, never drops.**  Messages stay PENDING in the outbox and go out when the
  pause is lifted.  A kill-switch that discarded messages would make operators reluctant to
  use it, which defeats the purpose.
- **Existence is the signal.**  The switch is a file; if it exists, delivery is paused.  No
  parsing, no truthy/falsy values, nothing that can be misread.  An unreadable file still
  pauses — for a stop control, ambiguity must resolve to *stop*.
- **The reason travels with it.**  Whatever the operator writes in the file is reported back
  in the pump's status line, so "why is nothing being delivered" is answerable from the logs
  rather than from memory.
"""

from dataclasses import dataclass
from pathlib import Path

#: Duraklatma kaydının okunabilir kısmı bu uzunlukta kırpılır; kill-switch dosyasına
#: yanlışlıkla büyük bir çıktı yazılırsa log satırını boğmasın.
MAX_REASON_CHARS = 300


@dataclass(frozen=True)
class PauseState:
    """Teslimatın durumu ve gerekçesi."""

    paused: bool
    reason: str | None = None

    def as_payload(self) -> dict:
        return {"delivery_paused": self.paused, "pause_reason": self.reason}


def read_pause_state(path: Path | None) -> PauseState:
    """Anahtarı oku. VARLIK duraklatma demektir; içerik yalnız gerekçedir.

    Yol verilmemişse duraklatma yoktur — anahtar opt-in'dir ve varsayılan davranışı
    değiştirmez.
    """
    if path is None:
        return PauseState(paused=False)
    try:
        if not path.exists():
            return PauseState(paused=False)
    except OSError as error:
        # Varlığı bile saptayamıyorsak durmak, bilinmeyen bir durumda göndermekten iyidir.
        return PauseState(paused=True, reason=f"anahtar dosyası okunamadı: {type(error).__name__}")
    try:
        reason = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        # Dosya var ama okunamıyor: duraklatma yine geçerlidir, gerekçe bilinmiyordur.
        return PauseState(paused=True, reason=f"gerekçe okunamadı: {type(error).__name__}")
    return PauseState(paused=True, reason=" ".join(reason.split())[:MAX_REASON_CHARS] or None)
