"""`decision-context/v1` producer model and RegimeSnapshot adapter."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from btc_radar.models.snapshot import RegimeSnapshot


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentV1(ContractModel):
    asset: Literal["BTC"] = "BTC"
    symbol: Literal["BTCUSDT"] = "BTCUSDT"
    market: Literal["USDT_PERPETUAL"] = "USDT_PERPETUAL"
    venue: Literal["binance"] = "binance"
    timeframe: Literal["1h"] = "1h"


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
    stale_sources: list[str] = Field(default_factory=list)
    missing_layers: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

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
    decision_role: Literal["context_only"] = "context_only"
    allowed_outputs: tuple[Literal["LONG"], Literal["SHORT"], Literal["WAIT"]] = (
        "LONG",
        "SHORT",
        "WAIT",
    )
    mode: Literal["paper"] = "paper"
    real_orders: Literal[False] = False


class DecisionContextV1(ContractModel):
    schema_version: Literal["decision-context/v1"] = "decision-context/v1"
    instrument: InstrumentV1 = Field(default_factory=InstrumentV1)
    as_of_utc: datetime
    snapshot: SnapshotContextV1
    data_quality: DataQualityV1
    usage: UsageV1 = Field(default_factory=UsageV1)

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


def build_decision_context(
    snapshot: RegimeSnapshot,
    *,
    required_layers: frozenset[str] = frozenset(),
    required_sources: frozenset[str] = frozenset(),
    additional_blockers: frozenset[str] = frozenset(),
) -> DecisionContextV1:
    """Adapt an immutable snapshot; only configured required gaps block direction."""
    stale_sources = sorted(set(snapshot.stale_sources))
    missing_layers = sorted(set(snapshot.missing_layers))
    if any(not blocker for blocker in additional_blockers):
        raise ValueError("additional_blockers boş etiket içeremez")
    blockers: list[str] = list(additional_blockers)

    if snapshot.direction is None or snapshot.fragility is None:
        blockers.append("scores_unavailable")
    if snapshot.regime_label == "veri_yetersiz":
        blockers.append("regime_unavailable")
    blockers.extend(
        f"missing_required_layer:{layer}" for layer in missing_layers if layer in required_layers
    )
    blockers.extend(
        f"stale_required_source:{source}" for source in stale_sources if source in required_sources
    )
    blockers = sorted(set(blockers))

    warnings = sorted(
        [
            *(
                f"missing_optional_layer:{layer}"
                for layer in missing_layers
                if layer not in required_layers
            ),
            *(
                f"stale_optional_source:{source}"
                for source in stale_sources
                if source not in required_sources
            ),
        ]
    )
    if blockers:
        status = "unavailable"
    elif warnings:
        status = "degraded"
    else:
        status = "healthy"

    return DecisionContextV1(
        as_of_utc=snapshot.as_of,
        snapshot=SnapshotContextV1(
            snapshot_id=snapshot.snapshot_id,
            data_cutoff_at_utc=snapshot.data_cutoff_at,
            computed_at_utc=snapshot.computed_at,
            direction=snapshot.direction,
            fragility=snapshot.fragility,
            confidence=snapshot.confidence,
            regime_label=snapshot.regime_label,
            feature_version=snapshot.feature_version,
            scoring_version=snapshot.scoring_version,
            weights_hash=snapshot.weights_hash,
            input_digest=snapshot.input_digest,
            content_hash=snapshot.content_hash,
        ),
        data_quality=DataQualityV1(
            status=status,
            directional_decision_allowed=not blockers,
            stale_sources=stale_sources,
            missing_layers=missing_layers,
            blockers=blockers,
            warnings=warnings,
        ),
    )
