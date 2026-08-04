"""Canonical serialization helpers shared by immutable decision artifacts."""

import hashlib
import json
from datetime import UTC, datetime


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timezone-aware UTC zorunlu")
    return value.astimezone(UTC).isoformat(timespec="seconds")
