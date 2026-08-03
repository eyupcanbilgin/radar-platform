"""config/*.yaml dosyalarının Pydantic sözleşmeleri.

Ağırlık ve eşikler her zaman config'den okunur; koda gömülmez (CLAUDE.md kural 3).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # compute_scores: güven bu eşiğin altındaysa rejim etiketi "veri yetersiz" (SPEC §4, araç 7)
    insufficient_below: int = Field(ge=0, le=100)


class FreshnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # f: beklenen periyot içinde 1.0, stale_multiple × periyot'ta 0 (core/snapshot.freshness)
    stale_multiple: float = Field(gt=1.0)
    stale_below_f: float = Field(ge=0.0, le=1.0)


class WeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    layers: dict[str, float]
    # SPEC §5.1'de kırılganlık ağırlığı (v) yön ağırlığından (w) ayrıdır. Tanımlanmazsa
    # layers kullanılır; Faz 1'de ayrışma gerekirse config'e eklenir, koda gömülmez.
    fragility_layers: dict[str, float] | None = None
    confidence: ConfidenceConfig
    freshness: FreshnessConfig

    @field_validator("layers")
    @classmethod
    def _layers_valid(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("layers boş olamaz")
        for name, w in v.items():
            if not 0.0 <= w <= 1.0:
                raise ValueError(f"'{name}' ağırlığı [0,1] aralığı dışında: {w}")
        total = sum(v.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"katman ağırlıkları toplamı 1.0 olmalı; bulunan: {total}")
        return v

    @field_validator("fragility_layers")
    @classmethod
    def _fragility_valid(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return None
        for name, w in v.items():
            if not 0.0 <= w <= 1.0:
                raise ValueError(f"fragility_layers['{name}'] [0,1] dışında: {w}")
        return v


class SignalRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    # Faz 1'de kural şeması sıkılaştırılacak (metrik → d/r dönüşümü, SPEC §5.1)
    rules: list[dict[str, Any]]
