"""Point-in-time-safe, immutable BTCUSDT 1h technical FeatureSnapshot v1."""

import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from decision_engine.canonical import sha256_hex
from enricher.decision_context import InstrumentV1

FEATURE_SCHEMA_VERSION = "feature-snapshot/v1"
FEATURE_VERSION = "btc-1h-core-v1"
LOOKBACK_BARS = 200


def btc_1h_instrument() -> InstrumentV1:
    return InstrumentV1(
        asset="BTC",
        symbol="BTCUSDT",
        market="USDT_PERPETUAL",
        venue="binance",
        timeframe="1h",
    )


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


class Candle1h(FrozenModel):
    """One public, closed 1h candle with its point-in-time availability."""

    open_time_utc: datetime
    close_time_utc: datetime
    available_at_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("open_time_utc", "close_time_utc", "available_at_utc")
    @classmethod
    def utc_aware(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def finite_number(cls, value: float, info) -> float:
        return _finite(value, info.field_name)

    @model_validator(mode="after")
    def closed_candle_is_coherent(self) -> "Candle1h":
        _require_hour_boundary(self.open_time_utc, "open_time_utc")
        _require_hour_boundary(self.close_time_utc, "close_time_utc")
        if self.close_time_utc - self.open_time_utc != timedelta(hours=1):
            raise ValueError("mum aralığı tam 1h olmalı")
        if self.available_at_utc < self.close_time_utc:
            raise ValueError("kapanmış mum kapanışından önce available olamaz")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC değerleri pozitif olmalı")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC geometrisi geçersiz")
        if self.low > self.high:
            raise ValueError("low high değerinden büyük olamaz")
        if self.volume < 0:
            raise ValueError("volume negatif olamaz")
        return self


class FeatureValuesV1(FrozenModel):
    close: float | None = None
    return_1h: float | None = None
    realized_vol_24h: float | None = None
    volume_ratio_24h: float | None = None
    ema20_distance_pct: float | None = None
    ema50_distance_pct: float | None = None
    atr14_sma_pct: float | None = None

    @field_validator("*")
    @classmethod
    def finite_when_present(cls, value: float | None, info) -> float | None:
        return None if value is None else _finite(value, info.field_name)


class FeatureSnapshotV1(FrozenModel):
    schema_version: Literal["feature-snapshot/v1"] = FEATURE_SCHEMA_VERSION
    snapshot_id: str = Field(pattern=r"^FS-[a-f0-9]{16}$")
    instrument: InstrumentV1 = Field(default_factory=btc_1h_instrument)
    as_of_utc: datetime
    data_cutoff_at_utc: datetime
    feature_version: Literal["btc-1h-core-v1"] = FEATURE_VERSION
    source_bars: int = Field(ge=0, le=LOOKBACK_BARS)
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    ready: bool
    missing_features: list[str]
    features: FeatureValuesV1
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of_utc", "data_cutoff_at_utc")
    @classmethod
    def hourly_utc(cls, value: datetime, info) -> datetime:
        return _require_hour_boundary(value, info.field_name)

    @field_validator("missing_features")
    @classmethod
    def sorted_unique_missing(cls, values: list[str]) -> list[str]:
        if any(not value for value in values):
            raise ValueError("boş missing_features etiketi yasak")
        if values != sorted(set(values)):
            raise ValueError("missing_features sıralı ve tekil olmalı")
        return values

    @model_validator(mode="after")
    def coherent_readiness(self) -> "FeatureSnapshotV1":
        if self.data_cutoff_at_utc > self.as_of_utc:
            raise ValueError("data_cutoff_at_utc as_of_utc sonrasında olamaz")
        if self.ready and self.missing_features:
            raise ValueError("ready snapshot missing feature taşıyamaz")
        if not self.ready and not self.missing_features:
            raise ValueError("hazır olmayan snapshot açık eksik nedeni taşımalı")
        return self


def _round(value: float) -> float:
    return round(float(value), 12)


def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _input_digest(candles: list[Candle1h]) -> str:
    payload = [candle.model_dump(mode="json") for candle in candles]
    return sha256_hex(payload)


def _snapshot_body(
    *,
    as_of: datetime,
    source_bars: int,
    input_digest: str,
    ready: bool,
    missing_features: list[str],
    features: FeatureValuesV1,
) -> dict:
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "instrument": btc_1h_instrument().model_dump(mode="json"),
        "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
        "data_cutoff_at_utc": as_of.isoformat().replace("+00:00", "Z"),
        "feature_version": FEATURE_VERSION,
        "source_bars": source_bars,
        "input_digest": input_digest,
        "ready": ready,
        "missing_features": missing_features,
        "features": features.model_dump(mode="json"),
    }


def feature_content_hash(snapshot: FeatureSnapshotV1) -> str:
    payload = snapshot.model_dump(mode="json", exclude={"content_hash"})
    return sha256_hex(payload)


def _feature_identity(*, as_of_utc: datetime, input_digest: str) -> dict:
    return {
        "instrument": btc_1h_instrument().model_dump(mode="json"),
        "as_of_utc": as_of_utc.isoformat().replace("+00:00", "Z"),
        "feature_version": FEATURE_VERSION,
        "input_digest": input_digest,
    }


def verify_feature_snapshot(snapshot: FeatureSnapshotV1) -> None:
    expected_id = (
        "FS-"
        + sha256_hex(
            _feature_identity(
                as_of_utc=snapshot.as_of_utc,
                input_digest=snapshot.input_digest,
            )
        )[:16]
    )
    if snapshot.snapshot_id != expected_id:
        raise ValueError(f"feature snapshot kimliği gövdeyle uyuşmuyor: {snapshot.snapshot_id}")
    expected_hash = feature_content_hash(snapshot)
    if snapshot.content_hash != expected_hash:
        raise ValueError(f"feature snapshot content_hash uyuşmuyor: {snapshot.snapshot_id}")


def build_feature_snapshot(candles: list[Candle1h], *, as_of: datetime) -> FeatureSnapshotV1:
    """Build from only candles closed and available by the exact hourly decision boundary."""
    as_of = _require_hour_boundary(as_of, "as_of")
    eligible = [
        candle
        for candle in candles
        if candle.close_time_utc <= as_of and candle.available_at_utc <= as_of
    ]
    eligible.sort(key=lambda candle: candle.close_time_utc)
    closes = [candle.close_time_utc for candle in eligible]
    if len(closes) != len(set(closes)):
        raise ValueError("aynı close_time için birden fazla mum var")
    selected = eligible[-LOOKBACK_BARS:]

    missing: list[str] = []
    if not selected or selected[-1].close_time_utc != as_of:
        missing.append("decision_candle")
    if len(selected) < LOOKBACK_BARS:
        missing.append(f"history_{LOOKBACK_BARS}")
    contiguous = all(
        right.close_time_utc - left.close_time_utc == timedelta(hours=1)
        for left, right in zip(selected, selected[1:], strict=False)
    )
    if selected and not contiguous:
        missing.append("contiguous_1h_history")

    values = FeatureValuesV1(close=_round(selected[-1].close) if selected else None)
    if not missing:
        close_values = [candle.close for candle in selected]
        log_returns = [
            math.log(current / previous)
            for previous, current in zip(close_values, close_values[1:], strict=False)
        ]
        volume_baseline = sum(candle.volume for candle in selected[-25:-1]) / 24.0
        if volume_baseline <= 0:
            missing.append("volume_baseline_24h")
        true_ranges = []
        for previous, current in zip(selected[-15:-1], selected[-14:], strict=True):
            true_ranges.append(
                max(
                    current.high - current.low,
                    abs(current.high - previous.close),
                    abs(current.low - previous.close),
                )
            )
        latest_close = close_values[-1]
        ema20 = _ema(close_values, 20)
        ema50 = _ema(close_values, 50)
        values = FeatureValuesV1(
            close=_round(latest_close),
            return_1h=_round(latest_close / close_values[-2] - 1.0),
            realized_vol_24h=_round(
                math.sqrt(sum(value * value for value in log_returns[-24:]) / 24.0)
            ),
            volume_ratio_24h=(
                _round(selected[-1].volume / volume_baseline) if volume_baseline > 0 else None
            ),
            ema20_distance_pct=_round((latest_close / ema20 - 1.0) * 100.0),
            ema50_distance_pct=_round((latest_close / ema50 - 1.0) * 100.0),
            atr14_sma_pct=_round((sum(true_ranges) / 14.0) / latest_close * 100.0),
        )

    missing = sorted(set(missing))
    ready = not missing
    digest = _input_digest(selected)
    body = _snapshot_body(
        as_of=as_of,
        source_bars=len(selected),
        input_digest=digest,
        ready=ready,
        missing_features=missing,
        features=values,
    )
    snapshot_id = "FS-" + sha256_hex(_feature_identity(as_of_utc=as_of, input_digest=digest))[:16]
    content_hash = sha256_hex({**body, "snapshot_id": snapshot_id})
    return FeatureSnapshotV1(
        snapshot_id=snapshot_id,
        as_of_utc=as_of,
        data_cutoff_at_utc=as_of,
        source_bars=len(selected),
        input_digest=digest,
        ready=ready,
        missing_features=missing,
        features=values,
        content_hash=content_hash,
    )
