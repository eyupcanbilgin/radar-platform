"""config/*.yaml dosyalarının Pydantic sözleşmeleri.

Ağırlık ve eşikler her zaman config'den okunur; koda gömülmez (CLAUDE.md kural 3).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class FragilityBand(BaseModel):
    """Yüzdelik eşiği → r katkısı. Eşik GÖRELİDİR (metodoloji §5.2): sabit fiyat/oran yok."""

    model_config = ConfigDict(extra="forbid")

    min_percentile: float = Field(ge=0.0, le=100.0)
    r: float = Field(ge=0.0, le=2.0)


class FeatureSpec(BaseModel):
    """Bir feature'ın veri ihtiyacı ve YETERLİ GEÇMİŞ şartı.

    `min_samples`, `min_span_days` ve `max_gap_seconds` birlikte "bu özelliği hesaplamak
    için elimizde yeterli geçmiş var mı" sorusunu yanıtlar. Şart sağlanmazsa feature
    üretilmez; eksik geçmiş sessizce nötr bir skora dönüşmez (fail-closed).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["abs_percentile", "change_abs_percentile"]
    metric: str = Field(min_length=1)
    lookback_days: float = Field(gt=0.0)
    expected_period_seconds: float = Field(gt=0.0)
    min_samples: int = Field(ge=2)
    min_span_days: float = Field(ge=0.0)
    max_gap_seconds: float = Field(gt=0.0)
    # Yalnız change_abs_percentile için: değişimin ölçüldüğü pencere (ör. 24 saat).
    change_window_seconds: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _change_window_matches_kind(self) -> "FeatureSpec":
        needs_window = self.kind == "change_abs_percentile"
        if needs_window and self.change_window_seconds is None:
            raise ValueError("change_abs_percentile için change_window_seconds zorunlu")
        if not needs_window and self.change_window_seconds is not None:
            raise ValueError(f"{self.kind} change_window_seconds kabul etmez")
        return self


class CollectionMetricSpec(BaseModel):
    """Operational cadence for a collected metric, without making it a scoring feature."""

    model_config = ConfigDict(extra="forbid")

    expected_period_seconds: float = Field(gt=0.0)
    max_gap_seconds: float = Field(gt=0.0)
    history_mode: Literal["backfill_and_live", "live_only"]


class RuleSpec(BaseModel):
    """Feature → kırılganlık katkısı kuralı (SPEC §5.1 metrik→r dönüşümü)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    # Yönsel kural henüz YOK: kabul edilmiş bir setup olmadan d üretmek uydurma olurdu.
    # Alan bilinçli olarak şemada duruyor ki "yön kapalı" bir karar olarak görünsün.
    directional: Literal[False] = False
    independence_group: str | None = None
    fragility_bands: list[FragilityBand] = Field(min_length=1)

    @field_validator("fragility_bands")
    @classmethod
    def _bands_descending_with_catch_all(cls, bands: list[FragilityBand]) -> list[FragilityBand]:
        thresholds = [band.min_percentile for band in bands]
        if thresholds != sorted(thresholds, reverse=True) or len(set(thresholds)) != len(
            thresholds
        ):
            raise ValueError("fragility_bands min_percentile'a göre azalan ve tekil olmalı")
        if thresholds[-1] != 0.0:
            raise ValueError("fragility_bands 0.0 eşikli bir yakalayıcı bant içermeli")
        return bands


class SignalRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    # Backfill satırının yayın anı = event_time + bu gecikme (ADR-0005). Kodda sabit değil:
    # tam saatte damgalanmış bir değerin aynı saatin kararına girmesini bu engeller.
    publication_lag_seconds: float = Field(default=0.0, ge=0.0)
    features: dict[str, FeatureSpec] = Field(default_factory=dict)
    # Collection health is not a feature declaration. A metric may be monitored here while
    # remaining completely absent from scoring and direction (ADR-0008).
    collection_metrics: dict[str, CollectionMetricSpec] = Field(default_factory=dict)
    rules: list[RuleSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules_reference_known_features(self) -> "SignalRulesConfig":
        identifiers = [rule.id for rule in self.rules]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("kural id'leri tekil olmalı")
        unknown = sorted({rule.feature for rule in self.rules} - set(self.features))
        if unknown:
            raise ValueError(f"tanımsız feature'a atıf yapan kural(lar): {unknown}")
        return self
