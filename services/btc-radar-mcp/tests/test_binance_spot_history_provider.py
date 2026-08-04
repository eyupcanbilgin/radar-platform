"""Binance spot history paging, availability and fail-loud contract tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.providers.binance_spot import OHLCV_METRIC
from btc_radar.providers.binance_spot_history import BinanceSpotHistoryProvider

FIXTURES = Path(__file__).parent / "fixtures" / "binance_spot"
KLINES_URL = "https://api.binance.com/api/v3/klines"
RETRIEVED_AT = datetime(2026, 8, 4, 22, 5, tzinfo=UTC)


def _fixture(name: str) -> list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
async def test_history_normalizes_every_closed_candle_with_publication_availability():
    route = respx.get(KLINES_URL).mock(
        return_value=httpx.Response(200, json=_fixture("klines_btcusdt_1h.json"))
    )
    start = datetime(2026, 8, 4, 20, tzinfo=UTC)
    end = datetime(2026, 8, 4, 22, tzinfo=UTC)
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotHistoryProvider(
            client,
            clock=lambda: RETRIEVED_AT,
            publication_lag_seconds=60,
        )
        observations = await provider.fetch(
            OHLCV_METRIC,
            start_time=start,
            end_time=end,
            limit=1000,
        )

    assert route.call_count == 1
    assert len(observations) == 10  # 2 kapanmış mum × OHLCV
    closes = [item for item in observations if item.metric == "spot_close"]
    assert [item.timestamp_utc for item in closes] == [start, start + timedelta(hours=1)]
    assert closes[0].available_at_utc == datetime(2026, 8, 4, 21, 0, 59, 999000, tzinfo=UTC)
    assert closes[0].retrieved_at_utc == RETRIEVED_AT
    assert closes[0].available_at_utc < closes[0].retrieved_at_utc
    request = route.calls[0].request
    assert request.url.params["symbol"] == "BTCUSDT"
    assert request.url.params["interval"] == "1h"
    assert request.url.params["startTime"] == str(int(start.timestamp() * 1000))
    assert request.url.params["endTime"] == str(int(end.timestamp() * 1000))


@respx.mock
async def test_history_drops_a_candle_that_has_not_closed_by_requested_end():
    respx.get(KLINES_URL).mock(
        return_value=httpx.Response(200, json=_fixture("klines_btcusdt_1h.json"))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotHistoryProvider(
            client,
            clock=lambda: RETRIEVED_AT,
            publication_lag_seconds=60,
        )
        observations = await provider.fetch(
            OHLCV_METRIC,
            start_time=datetime(2026, 8, 4, 20, tzinfo=UTC),
            end_time=datetime(2026, 8, 4, 21, 30, tzinfo=UTC),
            limit=10,
        )

    assert len(observations) == 5
    assert {item.timestamp_utc for item in observations} == {datetime(2026, 8, 4, 20, tzinfo=UTC)}


async def test_history_rejects_unknown_metric_bounds_limit_and_parameters():
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotHistoryProvider(client, publication_lag_seconds=60)
        with pytest.raises(ValueError, match="desteklenmeyen Binance spot gecmis"):
            await provider.fetch("spot_perp_basis")
        with pytest.raises(ValueError, match=r"limit \[1,1000\]"):
            await provider.fetch(OHLCV_METRIC, limit=1001)
        with pytest.raises(ValueError, match="timezone-aware"):
            await provider.fetch(OHLCV_METRIC, start_time=datetime(2026, 8, 4))
        with pytest.raises(ValueError, match="start_time end_time'dan once"):
            await provider.fetch(
                OHLCV_METRIC,
                start_time=RETRIEVED_AT,
                end_time=RETRIEVED_AT,
            )
        with pytest.raises(ValueError, match="desteklenmeyen.*parametreleri"):
            await provider.fetch(OHLCV_METRIC, window="1h")
