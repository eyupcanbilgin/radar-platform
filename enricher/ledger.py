"""Sinyal defteri (SQLite) — durum + geçiş kaydı, replay edilebilir kimlikle.

Sinyal kimliği (CR-002 P2-6): `BTC-S0002-YYYYMMDD-HHMM-L-01`
    varlık - strateji - mum kapanışı (UTC) - yön(L/S) - aynı mumdaki sıra

Defter tek yazma kapısıdır: durum yalnız `apply()` üzerinden değişir ve her değişiklik
`transitions` tablosuna sebep koduyla düşer. Elle UPDATE yolu bilerek yoktur (kural 9).
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from enricher.lifecycle import State, Transition, transition

_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id       TEXT PRIMARY KEY,
    asset           TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    direction       TEXT NOT NULL,
    candle_close_utc TEXT NOT NULL,
    state           TEXT NOT NULL,
    snapshot_id     TEXT,
    entry_reference REAL,
    invalidation    REAL,
    valid_until_utc TEXT,
    enter_tag       TEXT,
    degraded_flags  TEXT NOT NULL DEFAULT '',
    created_at_utc  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   TEXT NOT NULL,
    from_state  TEXT NOT NULL,
    to_state    TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    at_utc      TEXT NOT NULL,
    UNIQUE (signal_id, from_state, to_state, reason_code)
);
CREATE INDEX IF NOT EXISTS ix_tr_signal ON transitions (signal_id, id);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime yasak (UTC zorunlu)")
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def make_signal_id(
    *, asset: str, strategy: str, candle_close_utc: datetime, direction: str, seq: int = 1
) -> str:
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"yön LONG|SHORT olmalı, gelen: {direction!r}")
    stamp = candle_close_utc.astimezone(UTC).strftime("%Y%m%d-%H%M")
    return f"{asset}-{strategy}-{stamp}-{direction[0]}-{seq:02d}"


class SignalLedger:
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

    def __enter__(self) -> "SignalLedger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def create(
        self,
        *,
        signal_id: str,
        asset: str,
        strategy: str,
        direction: str,
        candle_close_utc: datetime,
        entry_reference: float | None = None,
        invalidation: float | None = None,
        valid_until_utc: datetime | None = None,
        snapshot_id: str | None = None,
        enter_tag: str | None = None,
        degraded_flags: list[str] | None = None,
        created_at_utc: datetime | None = None,
    ) -> bool:
        """Sinyali CANDIDATE olarak aç. Aynı signal_id ikinci kez → False (idempotent)."""
        if self.get(signal_id):
            return False
        self._conn.execute(
            """
            INSERT INTO signals (signal_id, asset, strategy, direction, candle_close_utc,
                                 state, snapshot_id, entry_reference, invalidation,
                                 valid_until_utc, enter_tag, degraded_flags, created_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                signal_id,
                asset,
                strategy,
                direction,
                _iso(candle_close_utc),
                State.CANDIDATE.value,
                snapshot_id,
                entry_reference,
                invalidation,
                _iso(valid_until_utc) if valid_until_utc else None,
                enter_tag,
                ",".join(degraded_flags or []),
                _iso(created_at_utc or datetime.now(UTC)),
            ),
        )
        self._conn.commit()
        return True

    def get(self, signal_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        return dict(row) if row else None

    def state_of(self, signal_id: str) -> State:
        row = self.get(signal_id)
        if not row:
            raise KeyError(f"bilinmeyen sinyal: {signal_id}")
        return State(row["state"])

    def apply(
        self, *, signal_id: str, target: State, reason_code: str, at_utc: datetime | None = None
    ) -> Transition | None:
        """TEK durum değiştirme kapısı. Geçersiz geçiş → IllegalTransition (kural 9)."""
        current = self.state_of(signal_id)
        tr = transition(
            signal_id=signal_id,
            current=current,
            target=target,
            reason_code=reason_code,
            at_utc=at_utc or datetime.now(UTC),
        )
        if tr is None:
            return None
        self._conn.execute(
            """
            INSERT OR IGNORE INTO transitions (signal_id, from_state, to_state, reason_code, at_utc)
            VALUES (?,?,?,?,?)
            """,
            (signal_id, tr.from_state.value, tr.to_state.value, tr.reason_code, _iso(tr.at_utc)),
        )
        self._conn.execute(
            "UPDATE signals SET state = ? WHERE signal_id = ?", (tr.to_state.value, signal_id)
        )
        self._conn.commit()
        return tr

    def history(self, signal_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM transitions WHERE signal_id = ? ORDER BY id ASC", (signal_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def in_state(self, state: State) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM signals WHERE state = ? ORDER BY candle_close_utc ASC, signal_id ASC",
            (state.value,),
        ).fetchall()
        return [dict(r) for r in rows]

    def next_seq(self, *, asset: str, strategy: str, candle_close_utc: datetime) -> int:
        """Aynı mumda aynı stratejiden birden fazla sinyal olursa sıra numarası."""
        n = self._conn.execute(
            "SELECT COUNT(*) FROM signals WHERE asset=? AND strategy=? AND candle_close_utc=?",
            (asset, strategy, _iso(candle_close_utc)),
        ).fetchone()[0]
        return int(n) + 1

    def find_existing(
        self,
        *,
        asset: str,
        strategy: str,
        candle_close_utc: datetime,
        direction: str,
        enter_tag: str | None,
    ) -> dict | None:
        """Aynı sinyalin doğal anahtarıyla aranması — webhook yeniden denemesi koruması.

        Webhook olaylarının kendi olay kimliği yoktur; bu beşli (varlık, strateji, mum
        kapanışı, yön, tetik etiketi) bir sinyali tekil olarak tanımlar. Aynı beşli ikinci
        kez gelirse bu YENİ sinyal değil, aynı sinyalin tekrar teslimidir. Sıra numarasına
        güvenmek bu durumda sinyali ikizlerdi (bu davranış testle yakalandı).
        """
        row = self._conn.execute(
            """
            SELECT * FROM signals
            WHERE asset=? AND strategy=? AND candle_close_utc=? AND direction=?
              AND IFNULL(enter_tag,'') = IFNULL(?,'')
            ORDER BY signal_id ASC LIMIT 1
            """,
            (asset, strategy, _iso(candle_close_utc), direction, enter_tag),
        ).fetchone()
        return dict(row) if row else None
