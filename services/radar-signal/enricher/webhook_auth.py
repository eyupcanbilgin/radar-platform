"""HMAC authentication and durable replay protection for webhook ingress."""

import hashlib
import hmac
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

SIGNATURE_PREFIX = "sha256="
NONCE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{16,128}$")

_DDL = """
CREATE TABLE IF NOT EXISTS webhook_nonces (
    nonce           TEXT PRIMARY KEY,
    request_time_utc TEXT NOT NULL,
    accepted_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_webhook_nonces_accepted
    ON webhook_nonces (accepted_at_utc);
"""


def signature_for(*, secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    if not secret:
        raise ValueError("webhook secret boş olamaz")
    message = timestamp.encode() + b"." + nonce.encode() + b"." + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(
    *, secret: str, timestamp: str, nonce: str, body: bytes, supplied: str
) -> bool:
    if not re.fullmatch(r"sha256=[a-f0-9]{64}", supplied):
        return False
    expected = signature_for(secret=secret, timestamp=timestamp, nonce=nonce, body=body)
    return hmac.compare_digest(expected, supplied)


def parse_request_time(timestamp: str) -> datetime:
    if not re.fullmatch(r"[0-9]{10}", timestamp):
        raise ValueError("webhook timestamp 10 haneli Unix saniyesi olmalı")
    return datetime.fromtimestamp(int(timestamp), tz=UTC)


def require_fresh(*, request_time: datetime, now: datetime, max_clock_skew_seconds: int) -> None:
    if max_clock_skew_seconds < 1:
        raise ValueError("max_clock_skew_seconds en az 1 olmalı")
    if now.tzinfo is None:
        raise ValueError("now timezone-aware olmalı")
    if abs((now.astimezone(UTC) - request_time).total_seconds()) > max_clock_skew_seconds:
        raise ValueError("webhook timestamp izin verilen saat penceresi dışında")


class NonceStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "NonceStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def reserve(
        self,
        *,
        nonce: str,
        request_time: datetime,
        accepted_at: datetime,
        retention_seconds: int,
    ) -> bool:
        if not NONCE_PATTERN.fullmatch(nonce):
            raise ValueError("webhook nonce biçimi geçersiz")
        if retention_seconds < 1:
            raise ValueError("nonce_retention_seconds en az 1 olmalı")
        cutoff = accepted_at.astimezone(UTC) - timedelta(seconds=retention_seconds)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                "DELETE FROM webhook_nonces WHERE accepted_at_utc < ?",
                (cutoff.isoformat(),),
            )
            self._conn.execute(
                """
                INSERT INTO webhook_nonces (nonce, request_time_utc, accepted_at_utc)
                VALUES (?, ?, ?)
                """,
                (
                    nonce,
                    request_time.astimezone(UTC).isoformat(),
                    accepted_at.astimezone(UTC).isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            self._conn.rollback()
            return False
        except Exception:
            self._conn.rollback()
            raise
