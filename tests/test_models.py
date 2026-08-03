"""RawObservation sözleşme testleri: UTC zorunluluğu + kalite sınırları."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from btc_radar.models.observation import RawObservation


def _obs(**over):
    base = dict(
        timestamp_utc=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        retrieved_at_utc=datetime.now(UTC),
        asset="BTC",
        venue="binance_futures",
        metric="open_interest",
        raw_value=95000.0,
        unit="BTC",
        source_group="derivatives",
        source_url="https://fapi.binance.com/fapi/v1/openInterest",
        quality=0.95,
    )
    base.update(over)
    return RawObservation(**base)


def test_aware_utc_accepted():
    obs = _obs()
    assert obs.timestamp_utc.tzinfo is not None
    assert obs.timestamp_utc.utcoffset().total_seconds() == 0


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError, match="naive"):
        _obs(timestamp_utc=datetime(2026, 8, 3, 12, 0))


def test_quality_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        _obs(quality=1.5)


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        _obs(surpriz_alan=1)
