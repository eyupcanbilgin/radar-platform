"""Bildirim outbox'ı — CR-002 P0-4 (kesintide kayıp yok, çift teslim yok).

Neden outbox: Telegram'a doğrudan göndermek iki hatayı davet eder — (1) kesintide mesaj
kaybolur, (2) yeniden denemede aynı mesaj iki kez gider. Outbox deseni mesajı ÖNCE
deftere yazar, teslimatı ayrı bir pompa (`pump`) yürütür ve `(signal_id, kind)` çifti
idempotency anahtarıdır: aynı sinyalin aynı türden bildirimi en fazla bir kez teslim edilir.

Teslimatçı dışarıdan verilir (üretimde Telegram, testte sahte gönderici); bu modül ağ
bilmez.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

PENDING = "PENDING"
SENT = "SENT"
DEAD = "DEAD"  # max_attempts tükendi; insan müdahalesi gerekir

_DDL = """
CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    body            TEXT NOT NULL,
    state           TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at_utc  TEXT NOT NULL,
    next_attempt_utc TEXT NOT NULL,
    sent_at_utc     TEXT,
    last_error      TEXT,
    UNIQUE (signal_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_outbox_due ON outbox (state, next_attempt_utc);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime yasak (UTC zorunlu)")
    return dt.astimezone(UTC).isoformat(timespec="seconds")


class Outbox:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        max_attempts: int = 20,
        backoff_seconds: list[int] | None = None,
        late_delivery_after_minutes: int = 5,
    ):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path) if self.path else ":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()
        self.max_attempts = max_attempts
        self.backoff = backoff_seconds or [5, 15, 30, 60, 120, 300]
        self.late_after = timedelta(minutes=late_delivery_after_minutes)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Outbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def enqueue(self, *, signal_id: str, kind: str, body: str, now: datetime) -> bool:
        """Mesajı kuyruğa al. Aynı (signal_id, kind) ikinci kez → False (idempotent)."""
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO outbox
                (signal_id, kind, body, state, attempts, created_at_utc, next_attempt_utc)
            VALUES (?,?,?,?,0,?,?)
            """,
            (signal_id, kind, body, PENDING, _iso(now), _iso(now)),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def due(self, now: datetime) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT * FROM outbox
            WHERE state = ? AND next_attempt_utc <= ?
            ORDER BY created_at_utc ASC, id ASC
            """,
            (PENDING, _iso(now)),
        ).fetchall()
        return [dict(r) for r in rows]

    def pump(self, sender: Callable[[str], None], *, now: datetime) -> dict:
        """Sırası gelen mesajları teslim etmeyi dene.

        `sender` istisna fırlatırsa mesaj PENDING kalır ve backoff'la yeniden planlanır;
        kayıp yoktur. Başarılı teslim SENT'e geçer ve bir daha ASLA gönderilmez.
        Kesinti uzadıysa gövdeye "geç teslim" notu eklenir (P2-7 ruhuyla: kullanıcı
        mesajın tazeliğini bilmeli).
        """
        stats = {"sent": 0, "failed": 0, "dead": 0}
        for row in self.due(now):
            body = row["body"]
            age = now - datetime.fromisoformat(row["created_at_utc"])
            if age >= self.late_after:
                mins = int(age.total_seconds() // 60)
                body = f"{body}\n[GEÇ TESLİM] Bu bildirim {mins} dk gecikmeyle iletildi."
            try:
                sender(body)
            except Exception as exc:  # teslimat hatası kayıp DEĞİLDİR
                attempts = row["attempts"] + 1
                if attempts >= self.max_attempts:
                    self._conn.execute(
                        "UPDATE outbox SET state=?, attempts=?, last_error=? WHERE id=?",
                        (DEAD, attempts, str(exc)[:300], row["id"]),
                    )
                    stats["dead"] += 1
                else:
                    delay = self.backoff[min(attempts - 1, len(self.backoff) - 1)]
                    self._conn.execute(
                        "UPDATE outbox SET attempts=?, next_attempt_utc=?, last_error=? WHERE id=?",
                        (
                            attempts,
                            _iso(now + timedelta(seconds=delay)),
                            str(exc)[:300],
                            row["id"],
                        ),
                    )
                    stats["failed"] += 1
                self._conn.commit()
                continue
            self._conn.execute(
                "UPDATE outbox SET state=?, sent_at_utc=?, attempts=? WHERE id=?",
                (SENT, _iso(now), row["attempts"] + 1, row["id"]),
            )
            self._conn.commit()
            stats["sent"] += 1
        return stats

    def counts(self) -> dict:
        rows = self._conn.execute("SELECT state, COUNT(*) c FROM outbox GROUP BY state").fetchall()
        return {r["state"]: r["c"] for r in rows}

    def get(self, *, signal_id: str, kind: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM outbox WHERE signal_id = ? AND kind = ?", (signal_id, kind)
        ).fetchone()
        return dict(row) if row else None
