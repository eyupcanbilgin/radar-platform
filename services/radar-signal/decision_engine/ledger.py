"""Atomic append-only storage for feature, context and hourly DecisionCard artifacts."""

import json
import math
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
from decision_engine.outcomes import DecisionOutcomeV1, verify_decision_outcome
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

CREATE TABLE IF NOT EXISTS decision_outcomes (
    outcome_id              TEXT PRIMARY KEY,
    decision_id             TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    timeframe               TEXT NOT NULL,
    as_of_utc               TEXT NOT NULL,
    horizon                 TEXT NOT NULL CHECK (horizon IN ('+1h', '+4h', '+24h')),
    horizon_close_utc       TEXT NOT NULL,
    decision_outcome        TEXT NOT NULL CHECK (decision_outcome IN ('LONG', 'SHORT', 'WAIT')),
    status                  TEXT NOT NULL CHECK (status IN ('evaluated', 'unavailable', 'pending')),
    reference_price         REAL,
    horizon_close_price     REAL,
    raw_return              REAL,
    net_return              REAL,
    mfe                     REAL,
    mae                     REAL,
    opportunity_return      REAL,
    data_health_ready       INTEGER NOT NULL CHECK (data_health_ready IN (0, 1)),
    data_health_payload     TEXT NOT NULL,
    candle_digest           TEXT,
    evaluator_version       TEXT NOT NULL,
    outcome_content_hash    TEXT NOT NULL,
    artifact_hash           TEXT NOT NULL,
    payload                 TEXT NOT NULL,
    recorded_at_utc         TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES hourly_decisions(decision_id),
    UNIQUE (decision_id, horizon)
);

CREATE INDEX IF NOT EXISTS ix_decision_outcomes_asof
    ON decision_outcomes (as_of_utc, horizon);

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

CREATE TRIGGER IF NOT EXISTS decision_outcomes_no_update
BEFORE UPDATE ON decision_outcomes
BEGIN
    SELECT RAISE(ABORT, 'decision_outcomes append-only: UPDATE yasak');
END;

CREATE TRIGGER IF NOT EXISTS decision_outcomes_no_delete
BEFORE DELETE ON decision_outcomes
BEGIN
    SELECT RAISE(ABORT, 'decision_outcomes append-only: DELETE yasak');
END;

CREATE TRIGGER IF NOT EXISTS decision_outcomes_no_conflicting_insert
BEFORE INSERT ON decision_outcomes
WHEN EXISTS (
    SELECT 1 FROM decision_outcomes
    WHERE outcome_id=NEW.outcome_id
       OR (decision_id=NEW.decision_id AND horizon=NEW.horizon)
)
BEGIN
    SELECT RAISE(ABORT, 'decision_outcomes append-only: çakışan INSERT yasak');
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

    def recent(self, *, limit: int) -> list[dict]:
        """Return a bounded, newest-first set of fully verified decision bundles."""
        if limit < 1:
            raise ValueError("limit en az 1 olmalı")
        rows = self._conn.execute(
            """
            SELECT decision_id FROM hourly_decisions
            ORDER BY as_of_utc DESC, decision_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            item = self.get(row["decision_id"])
            if item is not None:
                items.append(item)
        return items

    def feature_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()[0])

    def outcome_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM hourly_decisions GROUP BY outcome"
        ).fetchall()
        return {row["outcome"]: int(row["n"]) for row in rows}

    @staticmethod
    def _outcome_payloads(outcome: DecisionOutcomeV1) -> tuple[str, str, str]:
        data_health_payload = canonical_json(outcome.data_health.model_dump(mode="json"))
        outcome_payload = canonical_json(outcome.model_dump(mode="json"))
        artifact_hash = sha256_hex(json.loads(outcome_payload))
        return data_health_payload, outcome_payload, artifact_hash

    @staticmethod
    def _validate_stored_outcome_columns(item: dict, outcome: DecisionOutcomeV1) -> None:
        expected = {
            "outcome_id": outcome.outcome_id,
            "decision_id": outcome.decision_id,
            "symbol": outcome.instrument.symbol,
            "timeframe": outcome.instrument.timeframe,
            "as_of_utc": iso_utc(outcome.as_of_utc),
            "horizon": outcome.horizon,
            "horizon_close_utc": iso_utc(outcome.horizon_close_utc),
            "decision_outcome": outcome.decision_outcome,
            "status": outcome.status,
            "reference_price": outcome.reference_price,
            "horizon_close_price": outcome.horizon_close_price,
            "raw_return": outcome.raw_return,
            "net_return": outcome.net_return,
            "mfe": outcome.mfe,
            "mae": outcome.mae,
            "opportunity_return": outcome.opportunity_return,
            "data_health_ready": 1 if outcome.data_health.ready else 0,
            "candle_digest": outcome.data_health.candle_digest,
            "evaluator_version": outcome.evaluator_version,
            "outcome_content_hash": outcome.content_hash,
        }
        mismatches = [
            key
            for key, value in expected.items()
            if (
                item[key] != value
                and not (
                    isinstance(value, float)
                    and item[key] is not None
                    and math.isclose(item[key], value, abs_tol=1e-12)
                )
            )
        ]
        if mismatches:
            raise ImmutableDecisionError(
                "ledger outcome kolonları payload ile uyuşmuyor: " + ",".join(sorted(mismatches))
            )

    def record_outcome(
        self,
        outcome: DecisionOutcomeV1,
        *,
        recorded_at_utc: datetime | None = None,
    ) -> bool:
        """Atomically append decision outcome; exact retry is idempotent."""
        verify_decision_outcome(outcome)
        data_health_payload, outcome_payload, artifact_hash = self._outcome_payloads(outcome)
        recorded_at_utc = recorded_at_utc or datetime.now(UTC)

        try:
            self._conn.execute("BEGIN IMMEDIATE")
            decision_row = self._conn.execute(
                """
                SELECT symbol, timeframe, as_of_utc, outcome FROM hourly_decisions
                WHERE decision_id=?
                """,
                (outcome.decision_id,),
            ).fetchone()
            if not decision_row:
                raise ImmutableDecisionError(
                    f"outcome için bağlı karar bulunamadı: decision_id={outcome.decision_id}"
                )
            if (
                decision_row["symbol"] != outcome.instrument.symbol
                or decision_row["timeframe"] != outcome.instrument.timeframe
                or decision_row["as_of_utc"] != iso_utc(outcome.as_of_utc)
                or decision_row["outcome"] != outcome.decision_outcome
            ):
                raise ImmutableDecisionError(
                    f"outcome bağlı karar metadata ile uyuşmuyor: {outcome.decision_id}"
                )

            existing = self._conn.execute(
                """
                SELECT outcome_id, artifact_hash FROM decision_outcomes
                WHERE decision_id=? AND horizon=?
                """,
                (outcome.decision_id, outcome.horizon),
            ).fetchone()
            if existing:
                if (
                    existing["outcome_id"] == outcome.outcome_id
                    and existing["artifact_hash"] == artifact_hash
                ):
                    self._conn.rollback()
                    return False
                raise ImmutableDecisionError(
                    "aynı karar ve horizon için outcome yeniden yazılamaz: "
                    f"decision={outcome.decision_id} horizon={outcome.horizon} "
                    f"mevcut={existing['outcome_id']} gelen={outcome.outcome_id}"
                )

            self._conn.execute(
                """
                INSERT INTO decision_outcomes (
                    outcome_id, decision_id, symbol, timeframe, as_of_utc,
                    horizon, horizon_close_utc, decision_outcome, status,
                    reference_price, horizon_close_price, raw_return, net_return,
                    mfe, mae, opportunity_return, data_health_ready,
                    data_health_payload, candle_digest, evaluator_version,
                    outcome_content_hash, artifact_hash, payload, recorded_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    outcome.outcome_id,
                    outcome.decision_id,
                    outcome.instrument.symbol,
                    outcome.instrument.timeframe,
                    iso_utc(outcome.as_of_utc),
                    outcome.horizon,
                    iso_utc(outcome.horizon_close_utc),
                    outcome.decision_outcome,
                    outcome.status,
                    outcome.reference_price,
                    outcome.horizon_close_price,
                    outcome.raw_return,
                    outcome.net_return,
                    outcome.mfe,
                    outcome.mae,
                    outcome.opportunity_return,
                    1 if outcome.data_health.ready else 0,
                    data_health_payload,
                    outcome.data_health.candle_digest,
                    outcome.evaluator_version,
                    outcome.content_hash,
                    artifact_hash,
                    outcome_payload,
                    iso_utc(recorded_at_utc),
                ),
            )
            self._conn.commit()
            return True
        except Exception:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    def get_outcome(self, outcome_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT * FROM decision_outcomes WHERE outcome_id=?
            """,
            (outcome_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        item["data_health_payload"] = json.loads(item["data_health_payload"])
        outcome = DecisionOutcomeV1.model_validate(item["payload"])
        verify_decision_outcome(outcome)
        self._validate_stored_outcome_columns(item, outcome)
        _, _, artifact_hash = self._outcome_payloads(outcome)
        if item["artifact_hash"] != artifact_hash:
            raise ImmutableDecisionError(f"ledger outcome artifact_hash uyuşmuyor: {outcome_id}")
        return item

    def get_outcome_for_decision(self, decision_id: str, horizon: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT outcome_id FROM decision_outcomes
            WHERE decision_id=? AND horizon=?
            """,
            (decision_id, horizon),
        ).fetchone()
        return self.get_outcome(row["outcome_id"]) if row else None

    def get_outcomes_for_decision(self, decision_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT outcome_id FROM decision_outcomes
            WHERE decision_id=? ORDER BY horizon ASC
            """,
            (decision_id,),
        ).fetchall()
        outcomes = []
        for row in rows:
            res = self.get_outcome(row["outcome_id"])
            if res is not None:
                outcomes.append(res)
        return outcomes

    def outcome_record_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM decision_outcomes").fetchone()[0])

    def evaluated_outcome_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM decision_outcomes GROUP BY status"
        ).fetchall()
        return {row["status"]: int(row["n"]) for row in rows}
