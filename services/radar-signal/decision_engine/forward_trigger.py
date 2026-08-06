"""Append-only, outcome-blind F-0001 forward trigger observations."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from decision_engine.canonical import canonical_json, iso_utc, sha256_hex
from enricher.decision_context import DecisionContextV1
from scripts.fragility_event_rows import build_trigger_rows

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "f0001_forward_observation.yaml"

_DDL = """
PRAGMA recursive_triggers = ON;

CREATE TABLE IF NOT EXISTS f0001_trigger_observations (
    observation_id       TEXT PRIMARY KEY,
    as_of_utc            TEXT NOT NULL UNIQUE,
    status               TEXT NOT NULL CHECK (status IN ('observed', 'unavailable')),
    triggered            INTEGER CHECK (triggered IN (0, 1) OR triggered IS NULL),
    context_snapshot_id  TEXT NOT NULL,
    context_content_hash TEXT NOT NULL,
    observation_hash     TEXT NOT NULL,
    payload              TEXT NOT NULL,
    context_payload      TEXT NOT NULL,
    recorded_at_utc      TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS f0001_trigger_observations_no_update
BEFORE UPDATE ON f0001_trigger_observations
BEGIN
    SELECT RAISE(ABORT, 'f0001 trigger ledger append-only: UPDATE yasak');
END;

CREATE TRIGGER IF NOT EXISTS f0001_trigger_observations_no_delete
BEFORE DELETE ON f0001_trigger_observations
BEGIN
    SELECT RAISE(ABORT, 'f0001 trigger ledger append-only: DELETE yasak');
END;

CREATE TRIGGER IF NOT EXISTS f0001_trigger_observations_no_conflicting_insert
BEFORE INSERT ON f0001_trigger_observations
WHEN EXISTS (
    SELECT 1 FROM f0001_trigger_observations
    WHERE observation_id=NEW.observation_id OR as_of_utc=NEW.as_of_utc
)
BEGIN
    SELECT RAISE(ABORT, 'f0001 trigger ledger append-only: çakışan INSERT yasak');
END;
"""


class ImmutableTriggerObservationError(ValueError):
    pass


def load_forward_observation_config(path: Path | None = None) -> dict:
    config = yaml.safe_load((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    required_false = (
        "allow_historical_backfill",
        "read_forward_outcomes",
        "write_experiment_registry",
        "emit_alerts",
    )
    if config.get("hypothesis_id") != "F-0001" or config.get("mode") != "trigger_coverage_only":
        raise ValueError("F-0001 forward observation config kimliği bozuk")
    if config.get("baseline_variant") != "combined":
        raise ValueError("forward observation baseline variant combined olmalı")
    if any(config.get(field) is not False for field in required_false):
        raise ValueError("forward observation outcome/backfill/Registry/alert açamaz")
    if config.get("direction") is not None:
        raise ValueError("forward observation direction null olmalı")
    start = datetime.fromisoformat(config["observation_start_utc"].replace("Z", "+00:00"))
    if start.tzinfo is None or any((start.minute, start.second, start.microsecond)):
        raise ValueError("forward observation başlangıcı UTC saat sınırı olmalı")
    grace_seconds = config.get("coverage_grace_seconds")
    if not isinstance(grace_seconds, int) or not 0 <= grace_seconds < 3600:
        raise ValueError("forward coverage grace 0..3599 saniye olmalı")
    baseline_hash = str(config.get("baseline_context_set_sha256", ""))
    if len(baseline_hash) != 64 or any(char not in "0123456789abcdef" for char in baseline_hash):
        raise ValueError("forward observation baseline hash geçersiz")
    return config


def _rules_hash(config: dict) -> str:
    return hashlib.sha256(canonical_json(config["trigger"]).encode()).hexdigest()


def _context_row(context: DecisionContextV1) -> dict:
    return context.model_dump(mode="json")


def build_forward_observation(
    *,
    baseline_contexts: list[dict],
    prior_contexts: list[dict],
    context: DecisionContextV1,
    calibration_config: dict,
    observation_config: dict,
    previous_as_of_utc: datetime | None,
) -> dict:
    start = datetime.fromisoformat(
        observation_config["observation_start_utc"].replace("Z", "+00:00")
    ).astimezone(UTC)
    if context.as_of_utc < start:
        raise ValueError("forward observation başlangıcından önce backfill yasak")
    if context.snapshot.direction is not None or context.data_quality.directional_decision_allowed:
        raise ValueError("F-0001 forward context direction-null/kapalı olmalı")
    if previous_as_of_utc is not None and context.as_of_utc <= previous_as_of_utc:
        raise ValueError("forward observation saatleri ileri sırada eklenmeli")

    expected_previous = previous_as_of_utc or (start - timedelta(hours=1))
    gap_hours = int((context.as_of_utc - expected_previous) / timedelta(hours=1)) - 1
    blockers = []
    if gap_hours > 0:
        blockers.append(f"missing_forward_hours:{gap_hours}")

    current = _context_row(context)
    trigger_rows = build_trigger_rows(
        [*baseline_contexts, *prior_contexts, current], calibration_config
    )
    trigger = next(
        (row for row in trigger_rows if row["as_of"] == context.as_of_utc),
        None,
    )
    if context.snapshot.fragility is None:
        blockers.extend(f"context:{item}" for item in context.data_quality.blockers)
        blockers.append("fragility_unavailable")
    elif trigger is None:
        blockers.append("trigger_history_unavailable")

    status = "observed" if trigger is not None else "unavailable"
    semantic = {
        "schema_version": "f0001-forward-trigger/v1",
        "hypothesis_id": "F-0001",
        "as_of_utc": iso_utc(context.as_of_utc),
        "status": status,
        "fragility": context.snapshot.fragility,
        "trigger_percentile": trigger["percentile"] if trigger else None,
        "triggered": bool(trigger["triggered"]) if trigger else None,
        "gap_hours": gap_hours,
        "blockers": sorted(set(blockers)),
        "context_snapshot_id": context.snapshot.snapshot_id,
        "context_content_hash": context.snapshot.content_hash,
        "baseline_context_set_sha256": observation_config["baseline_context_set_sha256"],
        "trigger_rules_sha256": _rules_hash(calibration_config),
        "direction": None,
        "outcome_read": False,
        "registry_write": False,
        "alert_emitted": False,
    }
    semantic["observation_id"] = "FTR-" + sha256_hex(semantic)[:20]
    semantic["observation_hash"] = sha256_hex(semantic)
    return semantic


class ForwardTriggerLedger:
    def __init__(self, path: Path | str | None = None, *, read_only: bool = False):
        self.path = Path(path) if path else None
        if read_only and self.path is None:
            raise ValueError("read-only forward ledger için path zorunlu")
        if read_only and not self.path.exists():
            raise FileNotFoundError(f"forward trigger ledger bulunamadı: {self.path}")
        if self.path:
            if not read_only:
                self.path.parent.mkdir(parents=True, exist_ok=True)
        target = (
            f"file:{self.path.resolve()}?mode=ro"
            if read_only and self.path
            else str(self.path)
            if self.path
            else ":memory:"
        )
        self._conn = sqlite3.connect(target, uri=read_only)
        self._conn.row_factory = sqlite3.Row
        if not read_only:
            self._conn.executescript(_DDL)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ForwardTriggerLedger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _row(self, as_of_utc: datetime) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM f0001_trigger_observations WHERE as_of_utc=?",
            (iso_utc(as_of_utc),),
        ).fetchone()

    def latest_as_of(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT as_of_utc FROM f0001_trigger_observations ORDER BY as_of_utc DESC LIMIT 1"
        ).fetchone()
        return datetime.fromisoformat(row[0].replace("Z", "+00:00")) if row else None

    def contexts(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT context_payload FROM f0001_trigger_observations ORDER BY as_of_utc"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def record(
        self,
        observation: dict,
        context: DecisionContextV1,
        *,
        recorded_at_utc: datetime | None = None,
    ) -> bool:
        payload = canonical_json(observation)
        context_payload = canonical_json(_context_row(context))
        existing = self._row(context.as_of_utc)
        if existing:
            if (
                existing["observation_id"] == observation["observation_id"]
                and existing["observation_hash"] == observation["observation_hash"]
                and existing["payload"] == payload
                and existing["context_payload"] == context_payload
            ):
                return False
            raise ImmutableTriggerObservationError("aynı saat forward gözlemi yeniden yazılamaz")
        recorded = recorded_at_utc or datetime.now(UTC)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                INSERT INTO f0001_trigger_observations (
                    observation_id, as_of_utc, status, triggered, context_snapshot_id,
                    context_content_hash, observation_hash, payload, context_payload,
                    recorded_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation["observation_id"],
                    observation["as_of_utc"],
                    observation["status"],
                    int(observation["triggered"]) if observation["triggered"] is not None else None,
                    observation["context_snapshot_id"],
                    observation["context_content_hash"],
                    observation["observation_hash"],
                    payload,
                    context_payload,
                    iso_utc(recorded),
                ),
            )
            self._conn.commit()
            return True
        except Exception:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    def get(self, as_of_utc: datetime) -> dict | None:
        row = self._row(as_of_utc)
        if not row:
            return None
        item = dict(row)
        payload = json.loads(item["payload"])
        context = DecisionContextV1.model_validate_json(item["context_payload"])
        expected = {
            "as_of_utc": iso_utc(context.as_of_utc),
            "status": payload["status"],
            "triggered": int(payload["triggered"]) if payload["triggered"] is not None else None,
            "context_snapshot_id": context.snapshot.snapshot_id,
            "context_content_hash": context.snapshot.content_hash,
            "observation_id": payload["observation_id"],
            "observation_hash": payload["observation_hash"],
        }
        mismatches = [key for key, value in expected.items() if item[key] != value]
        semantic = {key: value for key, value in payload.items() if key != "observation_hash"}
        if mismatches or sha256_hex(semantic) != payload["observation_hash"]:
            raise ImmutableTriggerObservationError(
                "forward trigger ledger bütünlüğü bozuk: " + ",".join(sorted(mismatches))
            )
        return {**item, "payload": payload, "context_payload": context.model_dump(mode="json")}

    def count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM f0001_trigger_observations").fetchone()[0]
        )

    def observations_through(self, as_of_utc: datetime) -> list[dict]:
        """Return integrity-checked observations no later than an exact UTC hour."""
        if as_of_utc.tzinfo is None or any(
            (as_of_utc.minute, as_of_utc.second, as_of_utc.microsecond)
        ):
            raise ValueError("coverage as_of timezone-aware UTC saat sınırı olmalı")
        rows = self._conn.execute(
            "SELECT as_of_utc FROM f0001_trigger_observations "
            "WHERE as_of_utc <= ? ORDER BY as_of_utc",
            (iso_utc(as_of_utc),),
        ).fetchall()
        return [self.get(datetime.fromisoformat(row[0].replace("Z", "+00:00"))) for row in rows]


def observe_forward_context(
    *,
    ledger: ForwardTriggerLedger,
    baseline_contexts: list[dict],
    context: DecisionContextV1,
    calibration_config: dict,
    observation_config: dict,
) -> dict:
    """Build and append one context, returning an idempotent operator summary."""
    existing = ledger.get(context.as_of_utc)
    if existing is not None:
        if existing["context_payload"] != context.model_dump(mode="json"):
            raise ImmutableTriggerObservationError(
                "aynı saat farklı context ile yeniden gözlenemez"
            )
        return {"recorded": False, **existing["payload"]}
    observation = build_forward_observation(
        baseline_contexts=baseline_contexts,
        prior_contexts=ledger.contexts(),
        context=context,
        calibration_config=calibration_config,
        observation_config=observation_config,
        previous_as_of_utc=ledger.latest_as_of(),
    )
    return {"recorded": ledger.record(observation, context), **observation}
