"""Deterministic BTC 1h Decision Outcome Card (+1h, +4h, +24h) and verification."""

import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from decision_engine.canonical import sha256_hex
from decision_engine.features import btc_1h_instrument
from enricher.decision_context import InstrumentV1

OUTCOME_SCHEMA_VERSION = "decision-outcome/v1"
EVALUATOR_VERSION = "btc-1h-outcome-v1"

HORIZON_MAP = {
    "+1h": 1,
    "+4h": 4,
    "+24h": 24,
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware UTC zorunlu")
    return value.astimezone(UTC)


def _require_hour_boundary(value: datetime, field: str) -> datetime:
    value = _utc(value)
    if any((value.minute, value.second, value.microsecond)):
        raise ValueError(f"{field} kapanmış 1h mum sınırı olmalı")
    return value


def _finite(value: float, field: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} sonlu sayı olmalı")
    return value


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OutcomeDataHealthV1(FrozenModel):
    ready: bool
    missing_reasons: list[str]
    candle_count: int = Field(ge=0)
    expected_candle_count: int = Field(ge=1)
    first_candle_open_utc: datetime | None = None
    last_candle_close_utc: datetime | None = None
    candle_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("first_candle_open_utc", "last_candle_close_utc")
    @classmethod
    def utc_optional(cls, value: datetime | None, info) -> datetime | None:
        return _require_hour_boundary(value, info.field_name) if value is not None else None

    @field_validator("missing_reasons")
    @classmethod
    def sorted_unique_reasons(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("boş missing_reasons etiketi yasak")
        if values != sorted(set(values)):
            raise ValueError("missing_reasons sıralı ve tekil olmalı")
        return values

    @model_validator(mode="after")
    def coherent_health(self) -> "OutcomeDataHealthV1":
        if self.ready and self.missing_reasons:
            raise ValueError("ready health durumu missing_reasons taşıyamaz")
        if not self.ready and not self.missing_reasons:
            raise ValueError("hazır olmayan health durumu açık missing_reasons taşımalı")
        return self


class DecisionOutcomeV1(FrozenModel):
    schema_version: Literal["decision-outcome/v1"] = OUTCOME_SCHEMA_VERSION
    outcome_id: str = Field(pattern=r"^OUT-[a-f0-9]{16}$")
    decision_id: str = Field(pattern=r"^DEC-[a-f0-9]{16}$")
    instrument: InstrumentV1 = Field(default_factory=btc_1h_instrument)
    as_of_utc: datetime
    horizon: Literal["+1h", "+4h", "+24h"]
    horizon_close_utc: datetime
    decision_outcome: Literal["LONG", "SHORT", "WAIT"]
    status: Literal["evaluated", "unavailable", "pending"]
    reference_price: float | None = None
    horizon_close_price: float | None = None
    raw_return: float | None = None
    net_return: float | None = None
    mfe: float | None = None
    mae: float | None = None
    opportunity_return: float | None = None
    data_health: OutcomeDataHealthV1
    evaluator_version: Literal["btc-1h-outcome-v1"] = EVALUATOR_VERSION
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of_utc", "horizon_close_utc")
    @classmethod
    def hourly_utc(cls, value: datetime, info) -> datetime:
        return _require_hour_boundary(value, info.field_name)

    @field_validator(
        "reference_price",
        "horizon_close_price",
        "raw_return",
        "net_return",
        "mfe",
        "mae",
        "opportunity_return",
    )
    @classmethod
    def finite_optional(cls, value: float | None, info) -> float | None:
        return None if value is None else _finite(value, info.field_name)

    @model_validator(mode="after")
    def coherent_outcome(self) -> "DecisionOutcomeV1":
        expected_hours = HORIZON_MAP[self.horizon]
        if self.horizon_close_utc - self.as_of_utc != timedelta(hours=expected_hours):
            raise ValueError(
                f"horizon_close_utc {self.horizon} için as_of_utc+{expected_hours}h olmalı"
            )

        if self.status == "evaluated":
            if not self.data_health.ready:
                raise ValueError("evaluated status ready data_health gerektirir")
            if self.reference_price is None or self.reference_price <= 0:
                raise ValueError("evaluated status pozitif reference_price gerektirir")
            if self.horizon_close_price is None or self.horizon_close_price <= 0:
                raise ValueError("evaluated status pozitif horizon_close_price gerektirir")

            if self.decision_outcome == "WAIT":
                if (
                    self.raw_return is not None
                    or self.net_return is not None
                    or self.mfe is not None
                    or self.mae is not None
                ):
                    raise ValueError(
                        "WAIT kararları yönsel raw_return, net_return, MFE veya MAE taşıyamaz"
                    )
                if self.opportunity_return is None:
                    raise ValueError("evaluated WAIT kararı opportunity_return taşımalıdır")
            else:
                if self.raw_return is None or self.mfe is None or self.mae is None:
                    raise ValueError("evaluated yönsel karar raw_return, MFE ve MAE taşımalıdır")
                if self.opportunity_return is not None:
                    raise ValueError("yönsel karar opportunity_return taşıyamaz")
        elif self.status in {"unavailable", "pending"}:
            if self.decision_outcome == "WAIT" and (
                self.raw_return is not None
                or self.net_return is not None
                or self.mfe is not None
                or self.mae is not None
            ):
                raise ValueError("WAIT kararları yönsel metrik taşıyamaz")
            if self.status == "unavailable" and self.data_health.ready:
                raise ValueError("unavailable status ready olmayan data_health gerektirir")

        return self


def outcome_identity_dict(
    *,
    decision_id: str,
    horizon: Literal["+1h", "+4h", "+24h"],
    evaluator_version: str = EVALUATOR_VERSION,
) -> dict:
    return {
        "decision_id": decision_id,
        "horizon": horizon,
        "evaluator_version": evaluator_version,
    }


def compute_outcome_id(
    *,
    decision_id: str,
    horizon: Literal["+1h", "+4h", "+24h"],
    evaluator_version: str = EVALUATOR_VERSION,
) -> str:
    return (
        "OUT-"
        + sha256_hex(
            outcome_identity_dict(
                decision_id=decision_id,
                horizon=horizon,
                evaluator_version=evaluator_version,
            )
        )[:16]
    )


def outcome_content_hash(outcome: DecisionOutcomeV1) -> str:
    payload = outcome.model_dump(mode="json", exclude={"content_hash"})
    return sha256_hex(payload)


def verify_decision_outcome(outcome: DecisionOutcomeV1) -> None:
    expected_id = compute_outcome_id(
        decision_id=outcome.decision_id,
        horizon=outcome.horizon,
        evaluator_version=outcome.evaluator_version,
    )
    if outcome.outcome_id != expected_id:
        raise ValueError(f"outcome_id kimliği uyuşmuyor: {outcome.outcome_id}")
    expected_hash = outcome_content_hash(outcome)
    if outcome.content_hash != expected_hash:
        raise ValueError(f"outcome content_hash uyuşmuyor: {outcome.outcome_id}")
