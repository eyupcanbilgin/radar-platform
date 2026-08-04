"""Single-instance guard for the producer daemon.

Two daemons against the same PIT store are not a correctness problem — appends are idempotent
and the snapshot store serialises writers — but they are an operational one: doubled requests
against a rate-limited public endpoint is how an IP gets banned.

A stale lock is NOT cleared automatically.  Deciding "that PID is dead" from the outside is a
guess, and guessing wrong starts the second collector this file exists to prevent.  The error
tells the operator what to inspect and which file to remove.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class RunLockError(RuntimeError):
    """The lock is already held, or it cannot be created."""


@contextmanager
def exclusive_run_lock(path: Path | str, *, now: datetime | None = None) -> Iterator[Path]:
    """Hold an exclusive lock file for the duration of the block."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "acquired_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RunLockError(
            f"producer kilidi zaten tutuluyor: {lock_path} ({_describe(lock_path)}). "
            "Süreç gerçekten ölüyse dosyayı elle silin; otomatik temizlik yapılmaz."
        ) from error
    except OSError as error:
        raise RunLockError(f"producer kilidi oluşturulamadı: {lock_path}") from error

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        yield lock_path
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            # Kilit dosyası silinemezse bir sonraki başlatma açıkça hata verir; sessiz
            # devam etmek, kilidi hiç almamış gibi davranmaktan iyidir.
            pass


def _describe(lock_path: Path) -> str:
    try:
        content = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "içerik okunamadı"
    return f"pid={content.get('pid')} acquired_at={content.get('acquired_at')}"
