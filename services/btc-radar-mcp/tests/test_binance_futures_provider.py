"""Binance USD-M provider fixture, normalization, PIT, and retry tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.core.store import PointInTimeStore
from btc_radar.providers.binance_futures import BinanceFuturesProvider

FIXTURES = Path(__file__).parent / "fixtures" / "binance_usdm"
PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
RETRIEVED_AT = datetime(2026, 8, 4, 13, 28, 43, 500000, tzinfo=UTC)
# depth_btcusdt.json fixture'ının kendi E alanına yakın, ondan sonraki bir an.
DEPTH_RETRIEVED_AT = datetime(2026, 8, 4, 21, 51, 46, tzinfo=UTC)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _no_sleep(_delay: float) -> None:
    return None


@respx.mock
async def test_all_normalizes_three_metrics_with_two_public_requests():
    premium_route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    oi_route = respx.get(OPEN_INTEREST_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        observations = await provider.fetch("all")

    assert [obs.metric for obs in observations] == [
        "mark_price",
        "funding_rate",
        "open_interest",
    ]
    assert premium_route.call_count == 1
    assert oi_route.call_count == 1

    mark, funding, oi = observations
    assert mark.raw_value == pytest.approx(63877.74732609)
    assert mark.unit == "USDT/BTC"
    assert mark.timestamp_utc == datetime(2026, 8, 4, 13, 28, 43, tzinfo=UTC)
    assert mark.retrieved_at_utc == RETRIEVED_AT
    assert mark.available_at_utc == RETRIEVED_AT
    assert mark.venue == "binance_futures"
    assert mark.source_group == "derivatives"

    assert funding.raw_value == pytest.approx(0.00008438)
    assert funding.unit == "ratio"
    assert "2026-08-04T16:00:00+00:00" in funding.notes

    assert oi.raw_value == pytest.approx(109281.542)
    assert oi.unit == "BTC"
    assert oi.timestamp_utc == datetime(2026, 8, 4, 13, 28, 39, 824000, tzinfo=UTC)


@respx.mock
async def test_order_book_computes_spread_and_depth_from_top_levels():
    respx.get(DEPTH_URL).mock(return_value=httpx.Response(200, json=_fixture("depth_btcusdt.json")))
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: DEPTH_RETRIEVED_AT)
        observations = await provider.fetch("order_book")

    assert [obs.metric for obs in observations] == [
        "order_book_spread_bps",
        "order_book_depth_bid_usd",
        "order_book_depth_ask_usd",
    ]
    spread, depth_bid, depth_ask = observations
    assert spread.raw_value == pytest.approx(0.015578714179441054)
    assert spread.unit == "bps"
    assert depth_bid.raw_value == pytest.approx(119007.8075)
    assert depth_ask.raw_value == pytest.approx(1735652.7622)
    assert depth_bid.window == "top_20x20"
    assert spread.source_group == "execution_context"
    assert spread.timestamp_utc == datetime(2026, 8, 4, 21, 51, 45, 685000, tzinfo=UTC)
    # retrieved_at (DEPTH_RETRIEVED_AT), event_time'dan sonra: available_at onu kullanır.
    assert spread.available_at_utc == DEPTH_RETRIEVED_AT


@respx.mock
async def test_order_book_rejects_a_crossed_book():
    payload = _fixture("depth_btcusdt.json")
    crossed = {**payload, "bids": [["64300.00", "1.0"]], "asks": [["64100.00", "1.0"]]}
    respx.get(DEPTH_URL).mock(return_value=httpx.Response(200, json=crossed))
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: DEPTH_RETRIEVED_AT)
        with pytest.raises(ValueError, match="best_ask"):
            await provider.fetch("order_book")


@respx.mock
async def test_order_book_is_not_included_in_the_all_bundle():
    premium_route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    oi_route = respx.get(OPEN_INTEREST_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )
    depth_route = respx.get(DEPTH_URL).mock(
        return_value=httpx.Response(200, json=_fixture("depth_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        observations = await provider.fetch("all")
    assert [obs.metric for obs in observations] == [
        "mark_price",
        "funding_rate",
        "open_interest",
    ]
    assert depth_route.call_count == 0
    assert premium_route.call_count == 1
    assert oi_route.call_count == 1


@respx.mock
@pytest.mark.parametrize(
    ("metric", "url", "fixture_name"),
    [
        ("mark_price", PREMIUM_URL, "premium_index_btcusdt.json"),
        ("funding_rate", PREMIUM_URL, "premium_index_btcusdt.json"),
        ("open_interest", OPEN_INTEREST_URL, "open_interest_btcusdt.json"),
    ],
)
async def test_individual_metric_returns_exactly_one(metric: str, url: str, fixture_name: str):
    respx.get(url, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture(fixture_name))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        observations = await provider.fetch(metric, symbol="BTCUSDT")
    assert len(observations) == 1
    assert observations[0].metric == metric


async def test_call_schema_rejects_unknown_metric_symbol_and_parameter():
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client)
        with pytest.raises(ValueError, match="desteklenmeyen.*metrigi"):
            await provider.fetch("price")
        with pytest.raises(ValueError, match="yalniz BTCUSDT"):
            await provider.fetch("mark_price", symbol="ETHUSDT")
        with pytest.raises(ValueError, match="parametreleri"):
            await provider.fetch("mark_price", limit=1)


@respx.mock
async def test_available_at_uses_exchange_time_when_local_clock_is_behind():
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    local_retrieval = datetime(2026, 8, 4, 13, 28, 42, tzinfo=UTC)
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: local_retrieval)
        (mark,) = await provider.fetch("mark_price")

    assert mark.retrieved_at_utc == local_retrieval
    assert mark.available_at_utc == mark.timestamp_utc
    assert mark.available_at_utc > mark.retrieved_at_utc


@respx.mock
async def test_observation_fetched_after_as_of_is_excluded_by_pit_store():
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    as_of = datetime(2026, 8, 4, 13, 28, 43, tzinfo=UTC)
    retrieved_after_cutoff = as_of + timedelta(seconds=1)
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: retrieved_after_cutoff)
        observations = await provider.fetch("mark_price")

    with PointInTimeStore() as store:
        store.append(observations, provider=provider.name)
        assert store.read_as_of(as_of, asset="BTC") == []
        assert len(store.read_as_of(retrieved_after_cutoff, asset="BTC")) == 1


@respx.mock
async def test_negative_funding_is_valid_and_not_converted_to_percent():
    payload = {**_fixture("premium_index_btcusdt.json"), "lastFundingRate": "-0.000125"}
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        (funding,) = await provider.fetch("funding_rate")
    assert funding.raw_value == -0.000125


@respx.mock
@pytest.mark.parametrize("bad_value", [None, "", "NaN", "Infinity", True, "not-a-number"])
async def test_mark_price_parse_is_fail_loud(bad_value):
    payload = {**_fixture("premium_index_btcusdt.json"), "markPrice": bad_value}
    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        with pytest.raises(ValueError, match="markPrice"):
            await provider.fetch("mark_price")
    assert route.call_count == 1


@respx.mock
async def test_schema_drift_and_symbol_mismatch_are_fail_loud():
    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"})
    route.side_effect = [
        httpx.Response(200, json=[_fixture("premium_index_btcusdt.json")]),
        httpx.Response(
            200,
            json={**_fixture("premium_index_btcusdt.json"), "symbol": "ETHUSDT"},
        ),
    ]
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        with pytest.raises(ValueError, match="dict olmali"):
            await provider.fetch("mark_price")
        with pytest.raises(ValueError, match="symbol BTCUSDT"):
            await provider.fetch("mark_price")


@respx.mock
async def test_next_funding_time_is_validated_but_not_used_as_event_time():
    payload = {
        **_fixture("premium_index_btcusdt.json"),
        "nextFundingTime": 1785840000000,
    }
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        with pytest.raises(ValueError, match="nextFundingTime"):
            await provider.fetch("funding_rate")


@respx.mock
async def test_retryable_503_then_success_uses_bounded_backoff():
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"})
    route.side_effect = [
        httpx.Response(503, json={"code": -1000, "msg": "Service Unavailable"}),
        httpx.Response(200, json=_fixture("premium_index_btcusdt.json")),
    ]
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(
            client,
            clock=lambda: RETRIEVED_AT,
            sleep=record_sleep,
            retry_base_seconds=0.25,
        )
        observations = await provider.fetch("mark_price")

    assert observations[0].metric == "mark_price"
    assert route.call_count == 2
    assert delays == [0.25]


@respx.mock
async def test_transport_timeout_is_retried_for_public_get():
    route = respx.get(OPEN_INTEREST_URL, params={"symbol": "BTCUSDT"})
    route.side_effect = [
        httpx.ReadTimeout("read timed out"),
        httpx.Response(200, json=_fixture("open_interest_btcusdt.json")),
    ]
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT, sleep=_no_sleep)
        observations = await provider.fetch("open_interest")
    assert observations[0].metric == "open_interest"
    assert route.call_count == 2


@respx.mock
async def test_429_honors_short_retry_after():
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"})
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1.5"}),
        httpx.Response(200, json=_fixture("premium_index_btcusdt.json")),
    ]
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT, sleep=record_sleep)
        await provider.fetch("funding_rate")
    assert route.call_count == 2
    assert delays == [1.5]


@respx.mock
@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (418, {}),
        (400, {}),
        (429, {}),
        (429, {"Retry-After": "60"}),
        (429, {"Retry-After": "invalid"}),
    ],
)
async def test_non_retryable_or_long_rate_limit_fails_immediately(status: int, headers: dict):
    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(status, headers=headers)
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT, sleep=_no_sleep)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.fetch("mark_price")
    assert route.call_count == 1


@respx.mock
async def test_retry_exhaustion_preserves_http_status_error():
    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(503, json={"code": -1000})
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(
            client,
            clock=lambda: RETRIEVED_AT,
            sleep=_no_sleep,
            max_attempts=3,
        )
        with pytest.raises(httpx.HTTPStatusError) as captured:
            await provider.fetch("mark_price")
    assert captured.value.response.status_code == 503
    assert route.call_count == 3


@respx.mock
async def test_invalid_json_is_not_retried():
    route = respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, content=b"{")
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT, sleep=_no_sleep)
        with pytest.raises(ValueError, match="JSON"):
            await provider.fetch("mark_price")
    assert route.call_count == 1


@respx.mock
async def test_fixed_fixture_and_clock_are_deterministic():
    respx.get(PREMIUM_URL, params={"symbol": "BTCUSDT"}).mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        provider = BinanceFuturesProvider(client, clock=lambda: RETRIEVED_AT)
        first = await provider.fetch("funding_rate")
        second = await provider.fetch("funding_rate")
    assert [item.model_dump(mode="json") for item in first] == [
        item.model_dump(mode="json") for item in second
    ]


def test_constructor_rejects_unbounded_or_invalid_retry_configuration():
    with pytest.raises(ValueError, match="max_attempts"):
        BinanceFuturesProvider(max_attempts=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        BinanceFuturesProvider(timeout_seconds=float("inf"))
    with pytest.raises(ValueError, match="max_retry_wait_seconds"):
        BinanceFuturesProvider(max_retry_wait_seconds=-1)
