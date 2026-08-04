"""Atomic append-only storage for feature, context and hourly DecisionCard artifacts."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from decision_engine.canonical import canonical_json, iso_utc, sha256_hex
from decision_engine.decision import (
    DecisionCardV1,
    DirectionalSetup,
    build_hourly_decision,
    verify_decision_card,
)
from decision_engine.features import FeatureSnapshotV1, verify_feature_snapshot
from enricher.decision_context import DecisionContextV1

_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = ON;

CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id         TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    timeframe           TEXT NOT NULL,
    as_of_utc           TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    payload             TEXT NOT NULL,
    recorded_at_utc     TEXT NOT NULL,
    UNIQUE (symbol, timeframe, as_of_utc)
);

CREATE TABLE IF NOT EXISTS hourly_decisions (
    decision_id             TEXT PRIMARY KEY,
    symbol                  TEXT NOT NULL,
    timeframe               TEXT NOT NULL,
    as_of_utc               TEXT NOT NULL,
    outcome                 TEXT NOT NULL CHECK (outcome IN ('LONG','SHORT','WAIT')),
    feature_snapshot_id     TEXT NOT NULL,
    context_snapshot_id     TEXT,
    feature_content_hash    TEXT NOT NULL,
    context_content_hash    TEXT,
    decision_content_hash   TEXT NOT NULL,
    artifact_hash           TEXT NOT NULL,
    context_payload         TEXT,
    decision_payload        TEXT NOT NULL,
    recorded_at_utc         TEXT NOT NULL,
    FOREIGN KEY (feature_snapshot_id) REFERENCES feature_snapshots(snapshot_id),
    UNIQUE (symbol, timeframe, as_of_utc)
);

CREATE INDEX IF NOT EXISTS ix_hourly_decisions_asof
    ON hourly_decisions (as_of_utc, decision_id);

CREATE TRIGGER IF NOT EXISTS feature_snapshots_no_update
BEFORE UPDATE ON feature_snapshots
BEGIN
    SELECT RAISE(ABORT, 'feature_snapshots append-only: UPDATE yasak');
END;

CREATE TRIGGER IF NOT EXISTS feature_snapshots_no_delete
BEFORE DELETE ON feature_snapshots
BEGIN
    SELECT RAISE(ABORT, 'feature_snapshots append-only: DELETE yasak');
END;

CREATE TRIGGER IF NOT EXISTS feature_snapshots_no_conflicting_insert
BEFORE INSERT ON feature_snapshots
WHEN EXISTS (
    SELECT 1 FROM feature_snapshots
    WHERE snapshot_id=NEW.snapshot_id
       OR (symbol=NEW.symbol AND timeframe=NEW.timeframe AND as_of_utc=NEW.as_of_utc)
)
BEGIN
    SELECT RAISE(ABORT, 'feature_snapshots append-only: çakışan INSERT yasak');
END;

CREATE TRIGGER IF NOT EXISTS hourly_decisions_no_update
BEFORE UPDATE ON hourly_decisions
BEGIN
    SELECT RAISE(ABORT, 'hourly_decisions append-only: UPDATE yasak');
END;

CREATE TRIGGER IF NOT EXISTS hourly_decisions_no_delete
BEFORE DELETE ON hourly_decisions
BEGIN
    SELECT RAISE(ABORT, 'hourly_decisions append-only: DELETE yasak');
END;

CREATE TRIGGER IF NOT EXISTS hourly_decisions_no_conflicting_insert
BEFORE INSERT ON hourly_decisions
WHEN EXISTS (
    SELECT 1 FROM hourly_decisions
    WHERE decision_id=NEW.decision_id
       OR (symbol=NEW.symbol AND timeframe=NEW.timeframe AND as_of_utc=NEW.as_of_utc)
)
BEGIN
    SELECT RAISE(ABORT, 'hourly_decisions append-only: çakışan INSERT yasak');
END;
"""


class ImmutableDecisionError(ValueError):
    pass


class DecisionLedger:
    """One immutable feature+decision bundle per BTCUSDT 1h decision boundary."""

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

    def __enter__(self) -> "DecisionLedger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def _payloads(
        feature: FeatureSnapshotV1,
        context: DecisionContextV1 | None,
        decision: DecisionCardV1,
    ) -> tuple[str, str | None, str, str]:
        feature_payload = canonical_json(feature.model_dump(mode="json"))
        context_payload = (
            canonical_json(context.model_dump(mode="json")) if context is not None else None
        )
        decision_payload = canonical_json(decision.model_dump(mode="json"))
        semantic_context = json.loads(context_payload) if context_payload else None
        if semantic_context is not None:
            # MCP snapshot identity/content deliberately excludes wall-clock compute time.
            semantic_context["snapshot"].pop("computed_at_utc", None)
        artifact_hash = sha256_hex(
            {
                "feature": json.loads(feature_payload),
                "context": semantic_context,
                "decision": json.loads(decision_payload),
            }
        )
        return feature_payload, context_payload, decision_payload, artifact_hash

    @staticmethod
    def _validate_links(
        feature: FeatureSnapshotV1,
        context: DecisionContextV1 | None,
        decision: DecisionCardV1,
    ) -> None:
        verify_feature_snapshot(feature)
        verify_decision_card(decision)
        if feature.as_of_utc != decision.as_of_utc:
            raise ValueError("feature ve decision as_of_utc alanları uyuşmalı")
        if decision.feature_snapshot_id != feature.snapshot_id:
            raise ValueError("decision yanlış feature snapshot'a bağlı")
        if decision.feature_content_hash != feature.content_hash:
            raise ValueError("decision feature content hash alanı uyuşmuyor")
        if context is None:
            if decision.context_snapshot_id is not None:
                raise ValueError("context yokken decision context id taşıyamaz")
        else:
            if context.as_of_utc != decision.as_of_utc:
                raise ValueError("context ve decision as_of_utc alanları uyuşmalı")
            if decision.context_snapshot_id != context.snapshot.snapshot_id:
                raise ValueError("decision yanlış context snapshot'a bağlı")
            if decision.context_content_hash != context.snapshot.content_hash:
                raise ValueError("decision context content hash alanı uyuşmuyor")

        setup = (
            DirectionalSetup(**decision.candidate.model_dump())
            if decision.candidate is not None
            else None
        )
        expected = build_hourly_decision(
            feature,
            context,
            setup=setup,
            signal_commit=decision.signal_commit,
        )
        if expected != decision:
            raise ValueError(
                "decision card feature/context/setup girdilerinden yeniden üretilemiyor"
            )

    @staticmethod
    def _validate_stored_columns(
        item: dict,
        feature: FeatureSnapshotV1,
        context: DecisionContextV1 | None,
        decision: DecisionCardV1,
    ) -> None:
        expected = {
            "decision_id": decision.decision_id,
            "symbol": decision.instrument.symbol,
            "timeframe": decision.instrument.timeframe,
            "as_of_utc": iso_utc(decision.as_of_utc),
            "outcome": decision.outcome,
            "feature_snapshot_id": feature.snapshot_id,
            "context_snapshot_id": context.snapshot.snapshot_id if context else None,
            "feature_content_hash": feature.content_hash,
            "context_content_hash": context.snapshot.content_hash if context else None,
            "decision_content_hash": decision.content_hash,
            "stored_feature_snapshot_id": feature.snapshot_id,
            "stored_feature_symbol": feature.instrument.symbol,
            "stored_feature_timeframe": feature.instrument.timeframe,
            "stored_feature_as_of_utc": iso_utc(feature.as_of_utc),
            "stored_feature_content_hash": feature.content_hash,
        }
        mismatches = [key for key, value in expected.items() if item[key] != value]
        if mismatches:
            raise ImmutableDecisionError(
                "ledger kolonları payload ile uyuşmuyor: " + ",".join(sorted(mismatches))
            )

    def _put_feature(
        self,
        feature: FeatureSnapshotV1,
        *,
        payload: str,
        recorded_at_utc: datetime,
    ) -> bool:
        period = (
            feature.instrument.symbol,
            feature.instrument.timeframe,
            iso_utc(feature.as_of_utc),
        )
        existing = self._conn.execute(
            """
            SELECT snapshot_id, content_hash, payload FROM feature_snapshots
            WHERE symbol=? AND timeframe=? AND as_of_utc=?
            """,
            period,
        ).fetchone()
        if existing:
            if (
                existing["snapshot_id"] == feature.snapshot_id
                and existing["content_hash"] == feature.content_hash
                and existing["payload"] == payload
            ):
                return False
            raise ImmutableDecisionError(
                "aynı saat için feature snapshot yeniden yazılamaz: "
                f"{period[0]} {period[1]} {period[2]} mevcut={existing['snapshot_id']} "
                f"gelen={feature.snapshot_id}"
            )
        self._conn.execute(
            """
            INSERT INTO feature_snapshots (
                snapshot_id, symbol, timeframe, as_of_utc,
                content_hash, payload, recorded_at_utc
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                feature.snapshot_id,
                feature.instrument.symbol,
                feature.instrument.timeframe,
                period[2],
                feature.content_hash,
                payload,
                iso_utc(recorded_at_utc),
            ),
        )
        return True

    def record(
        self,
        *,
        feature: FeatureSnapshotV1,
        context: DecisionContextV1 | None,
        decision: DecisionCardV1,
        recorded_at_utc: datetime | None = None,
    ) -> bool:
        """Atomically append snapshot+decision; exact retry is idempotent."""
        self._validate_links(feature, context, decision)
        feature_payload, context_payload, decision_payload, artifact_hash = self._payloads(
            feature, context, decision
        )
        recorded_at_utc = recorded_at_utc or datetime.now(UTC)
        period = (
            decision.instrument.symbol,
            decision.instrument.timeframe,
            iso_utc(decision.as_of_utc),
        )

        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._put_feature(
                feature,
                payload=feature_payload,
                recorded_at_utc=recorded_at_utc,
            )
            existing = self._conn.execute(
                """
                SELECT decision_id, artifact_hash FROM hourly_decisions
                WHERE symbol=? AND timeframe=? AND as_of_utc=?
                """,
                period,
            ).fetchone()
            if existing:
                if (
                    existing["decision_id"] == decision.decision_id
                    and existing["artifact_hash"] == artifact_hash
                ):
                    self._conn.rollback()
                    return False
                raise ImmutableDecisionError(
                    "aynı saat için karar yeniden yazılamaz: "
                    f"{period[0]} {period[1]} {period[2]} mevcut={existing['decision_id']} "
                    f"gelen={decision.decision_id}"
                )
            self._conn.execute(
                """
                INSERT INTO hourly_decisions (
                    decision_id, symbol, timeframe, as_of_utc, outcome,
                    feature_snapshot_id, context_snapshot_id, feature_content_hash,
                    context_content_hash, decision_content_hash, artifact_hash,
                    context_payload, decision_payload, recorded_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    decision.decision_id,
                    decision.instrument.symbol,
                    decision.instrument.timeframe,
                    period[2],
                    decision.outcome,
                    feature.snapshot_id,
                    context.snapshot.snapshot_id if context else None,
                    feature.content_hash,
                    context.snapshot.content_hash if context else None,
                    decision.content_hash,
                    artifact_hash,
                    context_payload,
                    decision_payload,
                    iso_utc(recorded_at_utc),
                ),
            )
            self._conn.commit()
            return True
        except Exception:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    def get(self, decision_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT d.*,
                   f.snapshot_id AS stored_feature_snapshot_id,
                   f.symbol AS stored_feature_symbol,
                   f.timeframe AS stored_feature_timeframe,
                   f.as_of_utc AS stored_feature_as_of_utc,
                   f.content_hash AS stored_feature_content_hash,
                   f.payload AS feature_payload
            FROM hourly_decisions d
            JOIN feature_snapshots f ON f.snapshot_id=d.feature_snapshot_id
            WHERE d.decision_id=?
            """,
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["feature_payload"] = json.loads(item["feature_payload"])
        item["context_payload"] = (
            json.loads(item["context_payload"]) if item["context_payload"] else None
        )
        item["decision_payload"] = json.loads(item["decision_payload"])
        feature = FeatureSnapshotV1.model_validate(item["feature_payload"])
        context = (
            DecisionContextV1.model_validate(item["context_payload"])
            if item["context_payload"]
            else None
        )
        decision = DecisionCardV1.model_validate(item["decision_payload"])
        self._validate_links(feature, context, decision)
        self._validate_stored_columns(item, feature, context, decision)
        _, _, _, artifact_hash = self._payloads(feature, context, decision)
        if item["artifact_hash"] != artifact_hash:
            raise ImmutableDecisionError(f"ledger artifact_hash uyuşmuyor: {decision_id}")
        return item

    def get_for_period(self, *, as_of_utc: datetime) -> dict | None:
        row = self._conn.execute(
            """
            SELECT decision_id FROM hourly_decisions
            WHERE symbol='BTCUSDT' AND timeframe='1h' AND as_of_utc=?
            """,
            (iso_utc(as_of_utc),),
        ).fetchone()
        return self.get(row["decision_id"]) if row else None

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM hourly_decisions").fetchone()[0])

    def feature_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()[0])

    def outcome_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM hourly_decisions GROUP BY outcome"
        ).fetchall()
        return {row["outcome"]: int(row["n"]) for row in rows}
