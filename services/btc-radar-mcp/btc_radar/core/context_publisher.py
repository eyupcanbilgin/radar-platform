"""Immutable exact-hour ``decision-context/v1`` filesystem publisher.

The signal service reads one deterministic path and never falls back to ``latest``.
Publication therefore has two non-negotiable properties: readers must never observe a
partial JSON document and an already published hour must never be overwritten.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from btc_radar.core.snapshot import verify_regime_snapshot
from btc_radar.models.decision_context import DecisionContextV1, build_decision_context
from btc_radar.models.snapshot import RegimeSnapshot


class ContextPublishError(RuntimeError):
    """The context artifact could not be safely published."""


class ImmutableContextConflictError(ContextPublishError):
    """The exact hour already contains different semantic content."""


class CorruptContextArtifactError(ContextPublishError):
    """An existing exact-hour artifact is unreadable or violates the contract."""


@dataclass(frozen=True)
class PublishResult:
    status: Literal["created", "idempotent"]
    path: Path
    snapshot_id: str
    semantic_hash: str


def require_utc_hour(value: datetime, *, field: str = "as_of_utc") -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} timezone-aware UTC olmalı")
    value = value.astimezone(UTC)
    if any((value.minute, value.second, value.microsecond)):
        raise ValueError(f"{field} kapanmış UTC 1h sınırı olmalı")
    return value


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _semantic_payload(context: DecisionContextV1) -> dict:
    payload = context.model_dump(mode="json")
    # Wall-clock computation time is deliberately non-semantic, like SnapshotStore.
    payload["snapshot"].pop("computed_at_utc")
    return payload


def semantic_hash_of(context: DecisionContextV1) -> str:
    return hashlib.sha256(_canonical_json(_semantic_payload(context))).hexdigest()


def _artifact_bytes(context: DecisionContextV1) -> bytes:
    payload = context.model_dump(mode="json")
    return (
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


class ExactHourContextPublisher:
    """Publish one complete artifact with atomic visibility and no overwrite."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def path_for(self, *, as_of_utc: datetime) -> Path:
        as_of_utc = require_utc_hour(as_of_utc)
        return (
            self.root
            / "v1"
            / "BTCUSDT"
            / "1h"
            / f"{as_of_utc:%Y}"
            / f"{as_of_utc:%m}"
            / f"{as_of_utc:%d}"
            / f"{as_of_utc:%H}.json"
        )

    def _read_existing(self, path: Path, *, expected_as_of: datetime) -> DecisionContextV1:
        try:
            context = DecisionContextV1.model_validate_json(path.read_bytes())
        except (OSError, UnicodeError, ValidationError, ValueError) as error:
            raise CorruptContextArtifactError(
                f"mevcut exact-hour context doğrulanamıyor ve overwrite edilmeyecek: {path}"
            ) from error
        if context.as_of_utc != expected_as_of:
            raise CorruptContextArtifactError(
                f"mevcut context yol saatiyle uyuşmuyor ve overwrite edilmeyecek: {path}"
            )
        if context.snapshot.computed_at_utc < expected_as_of:
            raise CorruptContextArtifactError(
                f"mevcut context computed_at as_of öncesinde ve overwrite edilmeyecek: {path}"
            )
        return context

    def _existing_result(
        self,
        path: Path,
        *,
        context: DecisionContextV1,
        expected_as_of: datetime,
    ) -> PublishResult:
        existing = self._read_existing(path, expected_as_of=expected_as_of)
        incoming_hash = semantic_hash_of(context)
        if semantic_hash_of(existing) != incoming_hash:
            raise ImmutableContextConflictError(
                "DEĞİŞMEZ CONTEXT İHLALİ: exact-hour yolu farklı içerikle "
                f"yeniden yazılamaz: {path}"
            )
        return PublishResult(
            status="idempotent",
            path=path,
            snapshot_id=existing.snapshot.snapshot_id,
            semantic_hash=incoming_hash,
        )

    def publish(
        self,
        snapshot: RegimeSnapshot,
        *,
        expected_as_of_utc: datetime | None = None,
        required_layers: frozenset[str] = frozenset(),
        required_sources: frozenset[str] = frozenset(),
        additional_blockers: frozenset[str] = frozenset(),
    ) -> PublishResult:
        verify_regime_snapshot(snapshot)
        expected_as_of = require_utc_hour(expected_as_of_utc or snapshot.as_of)
        if snapshot.as_of != expected_as_of:
            raise ValueError(
                "snapshot as_of beklenen exact-hour ile uyuşmuyor: "
                f"{snapshot.as_of.isoformat()} != {expected_as_of.isoformat()}"
            )

        context = build_decision_context(
            snapshot,
            required_layers=required_layers,
            required_sources=required_sources,
            additional_blockers=additional_blockers,
        )
        path = self.path_for(as_of_utc=expected_as_of)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return self._existing_result(path, context=context, expected_as_of=expected_as_of)

        artifact = _artifact_bytes(context)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(artifact)
                handle.flush()
                os.fsync(handle.fileno())

            # Hard-link creation is same-filesystem, atomically visible and fails if the
            # destination exists on both NTFS and POSIX. os.replace() is intentionally
            # forbidden because it could overwrite an immutable hour.
            try:
                os.link(temp_path, path)
            except FileExistsError:
                return self._existing_result(path, context=context, expected_as_of=expected_as_of)
            except OSError as error:
                raise ContextPublishError(
                    "atomik no-overwrite hard-link oluşturulamadı; güvensiz fallback "
                    f"kullanılmadı: {path}"
                ) from error
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    # The final artifact is already complete. A leftover hidden temp link
                    # is operational litter, never a partially visible consumer artifact.
                    pass

        return PublishResult(
            status="created",
            path=path,
            snapshot_id=snapshot.snapshot_id,
            semantic_hash=semantic_hash_of(context),
        )
