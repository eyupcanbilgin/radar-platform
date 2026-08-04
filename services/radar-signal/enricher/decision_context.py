"""Strict `decision-context/v1` consumer and fail-closed directional gate."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentV1(ContractModel):
    asset: Literal["BTC"]
    symbol: Literal["BTCUSDT"]
    market: Literal["USDT_PERPETUAL"]
    venue: Literal["binance"]
    timeframe: Literal["1h"]


class SnapshotContextV1(ContractModel):
    snapshot_id: str = Field(pattern=r"^SNAP-[a-f0-9]{16}$")
    data_cutoff_at_utc: datetime
    computed_at_utc: datetime
    direction: float | None = Field(default=None, ge=-100, le=100)
    fragility: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0, le=100)
    regime_label: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    scoring_version: str = Field(min_length=1)
    weights_hash: str = Field(pattern=r"^[a-f0-9]{12,64}$")
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("data_cutoff_at_utc", "computed_at_utc")
    @classmethod
    def utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware UTC zorunlu")
        return value.astimezone(UTC)


class DataQualityV1(ContractModel):
    status: Literal["healthy", "degraded", "unavailable"]
    directional_decision_allowed: bool
    stale_sources: list[str]
    missing_layers: list[str]
    blockers: list[str]
    warnings: list[str]

    @field_validator("stale_sources", "missing_layers", "blockers", "warnings")
    @classmethod
    def sorted_unique(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("boş veri kalitesi etiketi yasak")
        if values != sorted(set(values)):
            raise ValueError("veri kalitesi listeleri sıralı ve tekil olmalı")
        return values

    @model_validator(mode="after")
    def coherent_gate(self) -> "DataQualityV1":
        if self.status == "healthy" and (
            not self.directional_decision_allowed or self.blockers or self.warnings
        ):
            raise ValueError("healthy veri kapısında blocker/uyarı olamaz ve yön açık olmalı")
        if self.status == "degraded" and (
            not self.directional_decision_allowed or self.blockers or not self.warnings
        ):
            raise ValueError("degraded veri yalnız uyarıyla yönsel kullanıma açık olabilir")
        if self.status == "unavailable" and (
            self.directional_decision_allowed or not self.blockers
        ):
            raise ValueError("unavailable veri blocker taşır ve yönsel kararı kapatır")
        return self


class UsageV1(ContractModel):
    decision_role: Literal["context_only"]
    allowed_outputs: tuple[Literal["LONG"], Literal["SHORT"], Literal["WAIT"]]
    mode: Literal["paper"]
    real_orders: Literal[False]


class DecisionContextV1(ContractModel):
    schema_version: Literal["decision-context/v1"]
    instrument: InstrumentV1
    as_of_utc: datetime
    snapshot: SnapshotContextV1
    data_quality: DataQualityV1
    usage: UsageV1

    @field_validator("as_of_utc")
    @classmethod
    def utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware UTC zorunlu")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def point_in_time_safe(self) -> "DecisionContextV1":
        if any((self.as_of_utc.minute, self.as_of_utc.second, self.as_of_utc.microsecond)):
            raise ValueError("as_of_utc kapanmış 1h mum sınırı olmalı")
        if self.snapshot.data_cutoff_at_utc > self.as_of_utc:
            raise ValueError("data_cutoff_at_utc as_of_utc sonrasında olamaz")
        return self


@dataclass(frozen=True)
class DirectionalGate:
    allowed: bool
    output_when_closed: Literal["WAIT"] | None
    reasons: tuple[str, ...]


def parse_decision_context(payload: dict, *, expected_as_of: datetime) -> DecisionContextV1:
    """Parse the wire payload and reject a context from a different decision candle."""
    if expected_as_of.tzinfo is None:
        raise ValueError("expected_as_of timezone-aware UTC olmalı")
    context = DecisionContextV1.model_validate(payload)
    if context.as_of_utc != expected_as_of.astimezone(UTC):
        raise ValueError(
            "decision context as_of uyuşmuyor: "
            f"beklenen={expected_as_of.astimezone(UTC).isoformat()}, "
            f"gelen={context.as_of_utc.isoformat()}"
        )
    return context


def directional_gate(context: DecisionContextV1) -> DirectionalGate:
    """Return the deterministic WAIT gate carried by the shared contract."""
    quality = context.data_quality
    if quality.directional_decision_allowed:
        return DirectionalGate(allowed=True, output_when_closed=None, reasons=())
    return DirectionalGate(
        allowed=False,
        output_when_closed="WAIT",
        reasons=tuple(quality.blockers),
    )
