"""Historical funding/OI provider: fixture normalization, backfill PIT semantics, errors."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.core.store import PointInTimeStore
from btc_radar.providers.binance_futures_history import (
    FUNDING_SETTLED_METRIC,
    OPEN_INTEREST_HOURLY_METRIC,
    OPEN_INTEREST_VALUE_HOURLY_METRIC,
    BinanceFuturesHistoryProvider,
    HistoryWindowError,
)

FIXTURES = Path(__file__).parent / "fixtures" / "binance_usdm"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
OI_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"

# Deliberately much later than the fixture events: a backfill runs long after the fact.
RETRIEVED_AT = datetime(2026, 8, 4, 14, 30, tzinfo=UTC)
LAG_SECONDS = 60.0

FIRST_FUNDING_AT = datetime(2026, 7, 31, 16, 0, tzinfo=UTC)
LAST_FUNDING_AT = datetime(2026, 8, 4, 8, 0, 0, 2000, tzinfo=UTC)
FIRST_OI_AT = datetime(2026, 8, 2, 15, 0, tzinfo=UTC)
LAST_OI_AT = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)


def _fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _provider(client: httpx.AsyncClient) -> BinanceFuturesHistoryProvider:
    return BinanceFuturesHistoryProvider(
        client,
        clock=lambda: RETRIEVED_AT,
        publication_lag_seconds=LAG_SECONDS,
    )


@respx.mock
async def test_funding_history_normalizes_settled_series():
    respx.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_fixture("funding_rate_history_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        observations = await _provider(client).fetch(FUNDING_SETTLED_METRIC, limit=1000)

    assert len(observations) == 12
    assert {obs.metric for obs in observations} == {FUNDING_SETTLED_METRIC}
    first, last = observations[0], observations[-1]
    assert first.timestamp_utc == FIRST_FUNDING_AT
    assert last.timestamp_utc == LAST_FUNDING_AT
    assert first.raw_value == pytest.approx(0.00005664)
    assert last.raw_value == pytest.approx(0.00006248)
    assert first.unit == "ratio"
    assert first.venue == "binance_futures"
    assert first.source_group == "derivatives"
    # The settlement interval is not something we request, so we do not claim it here.
    assert first.window is None
    assert "rate_type=Regular" in first.notes


@respx.mock
async def test_open_interest_history_yields_contract_and_notional_metrics():
    respx.get(OI_HIST_URL).mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_hist_1h_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        observations = await _provider(client).fetch(OPEN_INTEREST_HOURLY_METRIC, limit=500)

    assert len(observations) == 96  # 48 hourly buckets × 2 metrics
    contracts = [obs for obs in observations if obs.metric == OPEN_INTEREST_HOURLY_METRIC]
    notionals = [obs for obs in observations if obs.metric == OPEN_INTEREST_VALUE_HOURLY_METRIC]
    assert len(contracts) == len(notionals) == 48
    assert contracts[0].timestamp_utc == FIRST_OI_AT
    assert contracts[-1].timestamp_utc == LAST_OI_AT
    assert contracts[-1].raw_value == pytest.approx(109031.267)
    assert contracts[0].unit == "BTC"
    assert notionals[-1].raw_value == pytest.approx(6941322969.7812)
    assert notionals[0].unit == "USDT"
    # ``window`` states what we asked the API for, not an inference about the data.
    assert {obs.window for obs in observations} == {"1h"}


@respx.mock
async def test_backfilled_rows_are_stamped_with_publication_time_not_retrieval_time():
    respx.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_fixture("funding_rate_history_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        observations = await _provider(client).fetch(FUNDING_SETTLED_METRIC)

    first = observations[0]
    assert first.retrieved_at_utc == RETRIEVED_AT
    assert first.available_at_utc == FIRST_FUNDING_AT + timedelta(seconds=LAG_SECONDS)
    # A backfill must not claim the value became knowable only when we ran it.
    assert first.available_at_utc < first.retrieved_at_utc


@respx.mock
async def test_publication_lag_keeps_boundary_value_out_of_that_boundary_decision():
    respx.get(OI_HIST_URL).mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_hist_1h_btcusdt.json"))
    )
    async with httpx.AsyncClient() as client:
        observations = await _provider(client).fetch(OPEN_INTEREST_HOURLY_METRIC)

    with PointInTimeStore() as store:
        store.append(observations, provider="binance_futures_history")
        at_boundary = store.read_as_of(LAST_OI_AT, metrics=[OPEN_INTEREST_HOURLY_METRIC])
        after_lag = store.read_as_of(
            LAST_OI_AT + timedelta(seconds=LAG_SECONDS),
            metrics=[OPEN_INTEREST_HOURLY_METRIC],
        )

    # The 14:00 bucket is not usable for the 14:00 decision; the 13:00 one is.
    assert at_boundary[0]["event_time"].startswith("2026-08-04T13:00:00")
    assert after_lag[0]["event_time"].startswith("2026-08-04T14:00:00")


@respx.mock
async def test_retention_rejection_becomes_named_history_window_error():
    respx.get(OI_HIST_URL).mock(
        return_value=httpx.Response(
            400, json={"code": -1130, "msg": "parameter 'startTime' is invalid."}
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(HistoryWindowError, match="saklama penceresi"):
            await _provider(client).fetch(
                OPEN_INTEREST_HOURLY_METRIC,
                start_time=datetime(2026, 6, 1, tzinfo=UTC),
            )


@respx.mock
async def test_other_client_errors_stay_http_errors():
    respx.get(FUNDING_URL).mock(
        return_value=httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await _provider(client).fetch(FUNDING_SETTLED_METRIC)


@respx.mock
async def test_non_ascending_history_fails_loud():
    payload = _fixture("funding_rate_history_btcusdt.json")
    payload[3], payload[4] = payload[4], payload[3]
    respx.get(FUNDING_URL).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="artan sirada degil"):
            await _provider(client).fetch(FUNDING_SETTLED_METRIC)


@respx.mock
async def test_payload_shape_and_symbol_are_validated():
    async with httpx.AsyncClient() as client:
        provider = _provider(client)
        respx.get(FUNDING_URL).mock(return_value=httpx.Response(200, json={"symbol": "BTCUSDT"}))
        with pytest.raises(ValueError, match="list olmali"):
            await provider.fetch(FUNDING_SETTLED_METRIC)

        respx.get(FUNDING_URL).mock(return_value=httpx.Response(200, json=[["not", "a", "dict"]]))
        with pytest.raises(ValueError, match="dict kayitlardan"):
            await provider.fetch(FUNDING_SETTLED_METRIC)

        respx.get(FUNDING_URL).mock(
            return_value=httpx.Response(
                200,
                json=[{"symbol": "ETHUSDT", "fundingTime": 1785513600000, "fundingRate": "0.1"}],
            )
        )
        with pytest.raises(ValueError, match="symbol BTCUSDT"):
            await provider.fetch(FUNDING_SETTLED_METRIC)


async def test_call_schema_rejects_unknown_metric_symbol_limit_and_naive_time():
    async with httpx.AsyncClient() as client:
        provider = _provider(client)
        with pytest.raises(ValueError, match="desteklenmeyen Binance gecmis metrigi"):
            await provider.fetch("open_interest")
        with pytest.raises(ValueError, match="yalniz BTCUSDT"):
            await provider.fetch(FUNDING_SETTLED_METRIC, symbol="ETHUSDT")
        with pytest.raises(ValueError, match=r"limit \[1,1000\]"):
            await provider.fetch(FUNDING_SETTLED_METRIC, limit=1001)
        with pytest.raises(ValueError, match=r"limit \[1,500\]"):
            await provider.fetch(OPEN_INTEREST_HOURLY_METRIC, limit=501)
        with pytest.raises(ValueError, match="timezone-aware"):
            await provider.fetch(FUNDING_SETTLED_METRIC, start_time=datetime(2026, 8, 1))


async def test_publication_lag_is_required_and_non_negative():
    async with httpx.AsyncClient() as client:
        with pytest.raises(TypeError):
            BinanceFuturesHistoryProvider(client)  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="publication_lag_seconds"):
            BinanceFuturesHistoryProvider(client, publication_lag_seconds=-1)


@respx.mock
async def test_requested_window_is_sent_as_epoch_millis():
    route = respx.get(OI_HIST_URL).mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient() as client:
        await _provider(client).fetch(
            OPEN_INTEREST_HOURLY_METRIC,
            end_time=datetime(2026, 8, 4, 14, 0, tzinfo=UTC),
            limit=500,
        )
    request = route.calls[0].request
    assert request.url.params["endTime"] == "1785852000000"
    assert request.url.params["period"] == "1h"
    assert request.url.params["symbol"] == "BTCUSDT"
