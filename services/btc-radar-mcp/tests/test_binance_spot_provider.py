"""Binance spot OHLCV + spot/perp basis provider fixture and normalization tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.providers.binance_futures import BinanceFuturesProvider
from btc_radar.providers.binance_spot import BinanceSpotProvider

SPOT_FIXTURES = Path(__file__).parent / "fixtures" / "binance_spot"
FUTURES_FIXTURES = Path(__file__).parent / "fixtures" / "binance_usdm"
KLINES_URL = "https://api.binance.com/api/v3/klines"
TICKER_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
# kline[0] (20:00-21:00) kapanmış, kline[1] (21:00-22:00) 21:59:59.999'da kapanıyor.
RETRIEVED_AT = datetime(2026, 8, 4, 21, 5, 0, tzinfo=UTC)


def _spot_fixture(name: str):
    return json.loads((SPOT_FIXTURES / name).read_text(encoding="utf-8"))


def _futures_fixture(name: str):
    return json.loads((FUTURES_FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
async def test_ohlcv_uses_the_newest_closed_candle_and_drops_the_open_one():
    respx.get(KLINES_URL).mock(
        return_value=httpx.Response(200, json=_spot_fixture("klines_btcusdt_1h.json"))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotProvider(client, clock=lambda: RETRIEVED_AT)
        observations = await provider.fetch("ohlcv_1h")

    assert [obs.metric for obs in observations] == [
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "spot_volume",
    ]
    by_metric = {obs.metric: obs for obs in observations}
    assert by_metric["spot_open"].raw_value == pytest.approx(64233.35)
    assert by_metric["spot_high"].raw_value == pytest.approx(64420.00)
    assert by_metric["spot_low"].raw_value == pytest.approx(64001.68)
    assert by_metric["spot_close"].raw_value == pytest.approx(64341.00)
    assert by_metric["spot_volume"].raw_value == pytest.approx(558.35238)
    # Açık mumun (21:00-22:00, close=64218.00) kullanılmadığının kanıtı.
    assert by_metric["spot_close"].raw_value != pytest.approx(64218.00)

    close = by_metric["spot_close"]
    assert close.timestamp_utc == datetime(2026, 8, 4, 20, 0, tzinfo=UTC)  # openTime
    assert close.retrieved_at_utc == RETRIEVED_AT
    # retrieved_at, candle'ın close_time'ından sonra: available_at onu kullanır.
    assert close.available_at_utc == RETRIEVED_AT
    assert close.venue == "binance_spot"
    assert close.source_group == "spot"
    assert close.unit == "USDT/BTC"
    assert by_metric["spot_volume"].unit == "BTC"


@respx.mock
async def test_ohlcv_raises_when_every_candle_is_still_open():
    respx.get(KLINES_URL).mock(
        return_value=httpx.Response(200, json=_spot_fixture("klines_btcusdt_1h.json"))
    )
    too_early = datetime(2026, 8, 4, 20, 30, 0, tzinfo=UTC)  # ilk mum henüz kapanmadı
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotProvider(client, clock=lambda: too_early)
        with pytest.raises(ValueError, match="kapanmis mum yok"):
            await provider.fetch("ohlcv_1h")


@respx.mock
async def test_basis_combines_spot_ticker_and_injected_futures_mark_price():
    respx.get(TICKER_PRICE_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_spot_fixture("ticker_price_btcusdt.json"))
    )
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_futures_fixture("premium_index_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        futures = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        provider = BinanceSpotProvider(client, clock=lambda: RETRIEVED_AT, futures_provider=futures)
        [basis] = await provider.fetch("spot_perp_basis")

    # spot=64218.01, mark=63877.74732609 (mevcut premium_index fixture'ından)
    assert basis.metric == "spot_perp_basis"
    assert basis.unit == "%"
    assert basis.raw_value == pytest.approx((64218.01 - 63877.74732609) / 63877.74732609 * 100)
    assert basis.venue == "binance"
    assert basis.source_group == "derivatives"
    assert basis.retrieved_at_utc == RETRIEVED_AT
    assert basis.available_at_utc >= basis.timestamp_utc


@respx.mock
async def test_all_bundles_six_observations_and_reuses_injected_futures_provider():
    respx.get(KLINES_URL).mock(
        return_value=httpx.Response(200, json=_spot_fixture("klines_btcusdt_1h.json"))
    )
    respx.get(TICKER_PRICE_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_spot_fixture("ticker_price_btcusdt.json"))
    )
    premium_route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_futures_fixture("premium_index_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        futures = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        provider = BinanceSpotProvider(client, clock=lambda: RETRIEVED_AT, futures_provider=futures)
        observations = await provider.fetch("all")

    assert [obs.metric for obs in observations] == [
        "spot_open",
        "spot_high",
        "spot_low",
        "spot_close",
        "spot_volume",
        "spot_perp_basis",
    ]
    # Enjekte edilen futures provider paylaşıldı; ayrı bir premiumIndex isteği açılmadı.
    assert premium_route.call_count == 1


@respx.mock
async def test_rejects_unsupported_metric_and_symbol():
    async with httpx.AsyncClient() as client:
        provider = BinanceSpotProvider(client, clock=lambda: RETRIEVED_AT)
        with pytest.raises(ValueError, match="desteklenmeyen Binance spot metrigi"):
            await provider.fetch("unknown")
        with pytest.raises(ValueError, match="yalniz BTCUSDT"):
            await provider.fetch("ohlcv_1h", symbol="ETHUSDT")
