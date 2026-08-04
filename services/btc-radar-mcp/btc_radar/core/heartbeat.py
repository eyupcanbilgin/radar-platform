"""Append-only operational run log for the producer daemon.

A heartbeat answers "did the collector actually run, and did it succeed?" — a question the
PIT store cannot answer on its own.  An empty hour in the PIT store is ambiguous: the market
may have been quiet, the endpoint may have failed, or the process may have been dead.  This
log removes that ambiguity by recording every attempt, including the failed ones.

Design mirrors the PIT store on purpose:
- APPEND-ONLY. A failed run is never overwritten by the later success that "fixes" it;
  an outage stays in the record forever.
- Time is ISO-8601 UTC text, so lexical ordering is chronological ordering.

Deliberate limit: this file proves the PROCESS ran. It does not prove the DATA is complete —
that claim needs gap analysis over the collected series, which lives in ``core/coverage``.
Uptime is not coverage, and only the two together are evidence of uninterrupted operation.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = "1"

RunStatus = Literal["ok", "error", "skipped"]

_DDL = """
CREATE TABLE IF NOT EXISTS heartbeats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task           TEXT NOT NULL,
    status         TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT NOT NULL,
    duration_ms    REAL NOT NULL,
    as_of          TEXT,
    schema_version TEXT NOT NULL,
    detail         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hb_task_time ON heartbeats (task, finished_at);
CREATE INDEX IF NOT EXISTS ix_hb_task_as_of ON heartbeats (task, status, as_of);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("naive datetime yasak (CLAUDE.md kural 7)")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value).astimezone(UTC)


class HeartbeatStore:
    """Append-only daemon run log. ``path=None`` → in-memory (test)."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path) if self.path else ":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "HeartbeatStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def record(
        self,
        *,
        task: str,
        status: RunStatus,
        started_at: datetime,
        finished_at: datetime,
        as_of: datetime | None = None,
        detail: dict | None = None,
    ) -> int:
        # Zaman dilimi doğrulaması ÖNCE: naive/aware karşılaştırması TypeError verir ve
        # asıl sözleşme ihlalini (naive datetime) gizlerdi.
        started_iso, finished_iso = _iso(started_at), _iso(finished_at)
        if finished_iso < started_iso:
            raise ValueError("heartbeat finished_at started_at öncesinde olamaz")
        payload = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False, allow_nan=False)
        cursor = self._conn.execute(
            """
            INSERT INTO heartbeats
                (task, status, started_at, finished_at, duration_ms, as_of, schema_version, detail)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                task,
                status,
                started_iso,
                finished_iso,
                (finished_at - started_at).total_seconds() * 1000.0,
                None if as_of is None else _iso(as_of),
                SCHEMA_VERSION,
                payload,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def _row(self, sql: str, params: tuple) -> dict | None:
        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            return None
        decoded = dict(row)
        decoded["detail"] = json.loads(decoded["detail"])
        return decoded

    def last_run(self, task: str) -> dict | None:
        return self._row(
            "SELECT * FROM heartbeats WHERE task = ? ORDER BY finished_at DESC, id DESC LIMIT 1",
            (task,),
        )

    def last_success(self, task: str) -> dict | None:
        return self._row(
            "SELECT * FROM heartbeats WHERE task = ? AND status = 'ok' "
            "ORDER BY finished_at DESC, id DESC LIMIT 1",
            (task,),
        )

    def latest_success_as_of(self, task: str) -> datetime | None:
        """Bu görevin başarıyla işlediği EN GEÇ karar saati (publish için)."""
        row = self._conn.execute(
            "SELECT MAX(as_of) AS newest FROM heartbeats "
            "WHERE task = ? AND status = 'ok' AND as_of IS NOT NULL",
            (task,),
        ).fetchone()
        return _parse(row["newest"]) if row and row["newest"] else None

    def consecutive_failures(self, task: str) -> int:
        """Son başarıdan bu yana kaç kez üst üste hata alındı."""
        rows = self._conn.execute(
            "SELECT status FROM heartbeats WHERE task = ? AND status IN ('ok','error') "
            "ORDER BY finished_at DESC, id DESC LIMIT 100",
            (task,),
        ).fetchall()
        failures = 0
        for row in rows:
            if row["status"] != "error":
                break
            failures += 1
        return failures

    def summary(self, *, now: datetime, tasks: tuple[str, ...]) -> list[dict]:
        """Operatöre dönük özet: her görev için son durum ve son başarıdan bu yana geçen süre."""
        report = []
        for task in sorted(tasks):
            last = self.last_run(task)
            success = self.last_success(task)
            runs = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM heartbeats WHERE task = ?", (task,)
                ).fetchone()[0]
            )
            last_success_at = _parse(success["finished_at"]) if success else None
            report.append(
                {
                    "task": task,
                    "runs": runs,
                    "last_status": None if last is None else last["status"],
                    "last_finished_at": None if last is None else last["finished_at"],
                    "last_success_at": None if success is None else success["finished_at"],
                    "seconds_since_last_success": (
                        None
                        if last_success_at is None
                        else round((now.astimezone(UTC) - last_success_at).total_seconds(), 3)
                    ),
                    "consecutive_failures": self.consecutive_failures(task),
                    "last_error": (
                        None
                        if last is None or last["status"] != "error"
                        else last["detail"].get("error")
                    ),
                }
            )
        return report

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0])
