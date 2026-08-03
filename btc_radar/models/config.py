"""config/*.yaml dosyalarının Pydantic sözleşmeleri.

Ağırlık ve eşikler her zaman config'den okunur; koda gömülmez (CLAUDE.md kural 3).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # compute_scores: güven bu eşiğin altındaysa rejim etiketi "veri yetersiz" (SPEC §4, araç 7)
    insufficient_below: int = Field(ge=0, le=100)


class WeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    layers: dict[str, float]
    confidence: ConfidenceConfig

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


class SignalRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    # Faz 1'de kural şeması sıkılaştırılacak (metrik → d/r dönüşümü, SPEC §5.1)
    rules: list[dict[str, Any]]
