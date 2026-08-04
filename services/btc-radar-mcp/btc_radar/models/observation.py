"""SPEC §3.3 veri sözleşmesi: her provider çıkışı RawObservation listesidir."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawObservation(BaseModel):
    """Tek bir ham gözlem. Provider çıkışında bir kez doğrulanır; router ham dict taşır."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    timestamp_utc: datetime
    retrieved_at_utc: datetime
    # Sistemce İLK bilinebildiği an (CR-002 P0-1). Provider yayın gecikmesini biliyorsa
    # set eder; None ise PIT deposu retrieved_at_utc kullanır (çekim anından önce
    # bilinemezdi varsayımı — muhafazakâr taraf, ADR-0003).
    available_at_utc: datetime | None = None
    asset: str
    venue: str
    metric: str
    raw_value: float
    unit: str
    window: str | None = None
    source_group: str
    source_url: str
    quality: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

    @field_validator("timestamp_utc", "retrieved_at_utc", "available_at_utc")
    @classmethod
    def _utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("naive datetime yasak; timezone-aware UTC zorunlu (CLAUDE.md kural 7)")
        return v.astimezone(UTC)

    @property
    def effective_available_at(self) -> datetime:
        """PIT deposunun kullanacağı yayın anı: bilinmiyorsa çekim anı (muhafazakâr)."""
        return self.available_at_utc or self.retrieved_at_utc
