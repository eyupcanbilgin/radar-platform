"""Deterministic BTC 1h LONG/SHORT/WAIT DecisionCard construction."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from decision_engine.canonical import sha256_hex
from decision_engine.features import (
    FeatureSnapshotV1,
    btc_1h_instrument,
    verify_feature_snapshot,
)
from enricher.decision_context import DecisionContextV1, InstrumentV1, directional_gate

DECISION_SCHEMA_VERSION = "decision-card/v1"
POLICY_VERSION = "btc-1h-paper-v1"
POLICY_HASH = sha256_hex(
    {
        "policy_version": POLICY_VERSION,
        "gate_order": ["feature_ready", "context_directional_gate", "candidate_present"],
        "closed_output": "WAIT",
        "mode": "paper",
        "real_orders": False,
    }
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupReference(FrozenModel):
    setup_id: str = Field(pattern=r"^SETUP-[A-Za-z0-9._-]+$")
    hypothesis_id: str = Field(pattern=r"^S-[0-9]{4}[a-z]?$", min_length=1)
    rule_version: str = Field(min_length=1)
    as_of_utc: datetime
    feature_snapshot_id: str = Field(pattern=r"^FS-[a-f0-9]{16}$")
    feature_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    direction: Literal["LONG", "SHORT"]
    rationale: str = Field(min_length=1)
    counter_evidence: str = Field(min_length=1)

    @field_validator("as_of_utc")
    @classmethod
    def hourly_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("setup as_of_utc timezone-aware UTC olmalı")
        value = value.astimezone(UTC)
        if any((value.minute, value.second, value.microsecond)):
            raise ValueError("setup as_of_utc kapanmış 1h mum sınırı olmalı")
        return value


class DirectionalSetup(SetupReference):
    """A strategy-neutral candidate bound to one exact point-in-time feature artifact."""


class CandidateReference(SetupReference):
    """Immutable setup provenance copied into the resulting decision card."""


class DecisionCardV1(FrozenModel):
    schema_version: Literal["decision-card/v1"] = DECISION_SCHEMA_VERSION
    decision_id: str = Field(pattern=r"^DEC-[a-f0-9]{16}$")
    instrument: InstrumentV1 = Field(default_factory=btc_1h_instrument)
    as_of_utc: datetime
    outcome: Literal["LONG", "SHORT", "WAIT"]
    mode: Literal["paper"] = "paper"
    real_orders: Literal[False] = False
    feature_snapshot_id: str = Field(pattern=r"^FS-[a-f0-9]{16}$")
    feature_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_snapshot_id: str | None = Field(default=None, pattern=r"^SNAP-[a-f0-9]{16}$")
    context_content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    feature_version: str
    context_feature_version: str | None = None
    context_scoring_version: str | None = None
    policy_version: Literal["btc-1h-paper-v1"] = POLICY_VERSION
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    signal_commit: str = Field(pattern=r"^[a-f0-9]{12}$")
    candidate: CandidateReference | None = None
    reasons: list[str]
    blockers: list[str]
    warnings: list[str]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of_utc")
    @classmethod
    def hourly_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware UTC zorunlu")
        value = value.astimezone(UTC)
        if any((value.minute, value.second, value.microsecond)):
            raise ValueError("as_of_utc kapanmış 1h mum sınırı olmalı")
        return value

    @field_validator("reasons", "blockers", "warnings")
    @classmethod
    def sorted_unique(cls, values: list[str], info) -> list[str]:
        if any(not value for value in values):
            raise ValueError(f"{info.field_name} boş etiket taşıyamaz")
        if values != sorted(set(values)):
            raise ValueError(f"{info.field_name} sıralı ve tekil olmalı")
        return values

    @model_validator(mode="after")
    def coherent_decision(self) -> "DecisionCardV1":
        if not self.reasons:
            raise ValueError("karar en az bir gerekçe taşımalı")
        if self.outcome in {"LONG", "SHORT"}:
            if self.candidate is None or self.candidate.direction != self.outcome:
                raise ValueError("yönsel karar aynı yönde aday setup gerektirir")
            if self.blockers:
                raise ValueError("blocker varken yönsel karar üretilemez")
            if self.context_snapshot_id is None:
                raise ValueError("yönsel karar context snapshot gerektirir")
        if (self.context_snapshot_id is None) != (self.context_content_hash is None):
            raise ValueError("context snapshot id ve hash birlikte bulunmalı veya boş olmalı")
        return self


def _candidate_reference(setup: DirectionalSetup | None) -> CandidateReference | None:
    if setup is None:
        return None
    return CandidateReference(**setup.model_dump())


def decision_content_hash(card: DecisionCardV1) -> str:
    return sha256_hex(card.model_dump(mode="json", exclude={"content_hash"}))


def verify_decision_card(card: DecisionCardV1) -> None:
    expected_id = (
        "DEC-"
        + sha256_hex(
            {
                "instrument": card.instrument.model_dump(mode="json"),
                "as_of_utc": card.as_of_utc.isoformat().replace("+00:00", "Z"),
                "mode": card.mode,
            }
        )[:16]
    )
    if card.decision_id != expected_id:
        raise ValueError(f"decision_id gövdeyle uyuşmuyor: {card.decision_id}")
    if card.content_hash != decision_content_hash(card):
        raise ValueError(f"decision content_hash uyuşmuyor: {card.decision_id}")


def build_hourly_decision(
    feature_snapshot: FeatureSnapshotV1,
    context: DecisionContextV1 | None,
    *,
    setup: DirectionalSetup | None = None,
    signal_commit: str,
) -> DecisionCardV1:
    """Combine feature/context gates; absence of a candidate is a first-class WAIT."""
    verify_feature_snapshot(feature_snapshot)
    if setup is not None:
        if setup.as_of_utc != feature_snapshot.as_of_utc:
            raise ValueError("setup ve feature aynı as_of_utc mumuna ait olmalı")
        if setup.feature_snapshot_id != feature_snapshot.snapshot_id:
            raise ValueError("setup yanlış feature snapshot'a bağlı")
        if setup.feature_content_hash != feature_snapshot.content_hash:
            raise ValueError("setup feature content hash alanı uyuşmuyor")
    if context is not None:
        if feature_snapshot.as_of_utc != context.as_of_utc:
            raise ValueError("feature ve context aynı as_of_utc mumuna ait olmalı")
        if feature_snapshot.instrument != context.instrument:
            raise ValueError("feature ve context instrument alanları uyuşmalı")

    blockers = [f"feature:{item}" for item in feature_snapshot.missing_features]
    if context is None:
        blockers.append("context:missing")
        warnings: list[str] = []
    else:
        context_gate = directional_gate(context)
        blockers.extend(f"context:{item}" for item in context_gate.reasons)
        warnings = sorted(set(context.data_quality.warnings))
    blockers = sorted(set(blockers))

    if blockers:
        outcome: Literal["LONG", "SHORT", "WAIT"] = "WAIT"
        reasons = ["directional_gate_closed"]
    elif setup is None:
        outcome = "WAIT"
        reasons = ["no_directional_setup"]
    else:
        outcome = setup.direction
        reasons = [f"candidate:{setup.setup_id}"]

    body = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "instrument": feature_snapshot.instrument.model_dump(mode="json"),
        "as_of_utc": feature_snapshot.as_of_utc.isoformat().replace("+00:00", "Z"),
        "outcome": outcome,
        "mode": "paper",
        "real_orders": False,
        "feature_snapshot_id": feature_snapshot.snapshot_id,
        "feature_content_hash": feature_snapshot.content_hash,
        "context_snapshot_id": context.snapshot.snapshot_id if context else None,
        "context_content_hash": context.snapshot.content_hash if context else None,
        "feature_version": feature_snapshot.feature_version,
        "context_feature_version": context.snapshot.feature_version if context else None,
        "context_scoring_version": context.snapshot.scoring_version if context else None,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_HASH,
        "signal_commit": signal_commit,
        "candidate": (
            _candidate_reference(setup).model_dump(mode="json") if setup is not None else None
        ),
        "reasons": reasons,
        "blockers": blockers,
        "warnings": warnings,
    }
    decision_id = (
        "DEC-"
        + sha256_hex(
            {
                "instrument": body["instrument"],
                "as_of_utc": body["as_of_utc"],
                "mode": body["mode"],
            }
        )[:16]
    )
    content_hash = sha256_hex({**body, "decision_id": decision_id})
    return DecisionCardV1(
        decision_id=decision_id,
        as_of_utc=feature_snapshot.as_of_utc,
        outcome=outcome,
        feature_snapshot_id=feature_snapshot.snapshot_id,
        feature_content_hash=feature_snapshot.content_hash,
        context_snapshot_id=context.snapshot.snapshot_id if context else None,
        context_content_hash=context.snapshot.content_hash if context else None,
        feature_version=feature_snapshot.feature_version,
        context_feature_version=context.snapshot.feature_version if context else None,
        context_scoring_version=context.snapshot.scoring_version if context else None,
        policy_hash=POLICY_HASH,
        signal_commit=signal_commit,
        candidate=_candidate_reference(setup),
        reasons=reasons,
        blockers=blockers,
        warnings=warnings,
        content_hash=content_hash,
    )
