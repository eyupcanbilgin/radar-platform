"""Değişmez rejim snapshot'ı — CR-002 P0-1 veri sözleşmesi.

radar-signal ASLA "latest" istemez: `as_of=<15m mum kapanışı>` ister ve ürettiği
sinyale `snapshot_id` yazar. Böylece üç ay sonra "bu sinyal hangi rejim resmine
bakarak üretildi" sorusu bit-bit cevaplanabilir.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegimeSnapshot(BaseModel):
    """Bir karar anının değişmez rejim fotoğrafı."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    as_of: datetime  # karar anı (mum kapanışı)
    data_cutoff_at: datetime  # bu andan sonraki hiçbir veri kullanılmadı (= as_of)
    computed_at: datetime  # duvar saati; içerik hash'ine GİRMEZ (replay'i bozardı)

    direction: float | None = Field(default=None, ge=-100.0, le=100.0)
    fragility: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=100.0)
    regime_label: str

    feature_version: str
    scoring_version: str
    weights_hash: str
    input_digest: str  # kullanılan PIT satırlarının parmak izi
    content_hash: str  # değişmezlik denetimi (computed_at hariç tüm alanlar)

    stale_sources: list[str] = Field(default_factory=list)
    missing_layers: list[str] = Field(default_factory=list)
    breakdown: list[dict] = Field(default_factory=list)
    # Feature kanıtı: örneklem sayısı, kapsanan süre, en büyük boşluk, tazelik. Skor
    # değişmez kayda bağlıdır ki "fragility=62" üç ay sonra da yanlışlanabilir olsun
    # (feature_version 0.3.0'dan itibaren içerik hash'ine dahildir).
    evidence: list[dict] = Field(default_factory=list)

    @field_validator("as_of", "data_cutoff_at", "computed_at")
    @classmethod
    def _utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("naive datetime yasak; timezone-aware UTC zorunlu")
        return v.astimezone(UTC)
