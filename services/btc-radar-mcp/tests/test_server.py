"""server.py sözleşme testleri: shape(), classify_tool_error(), get_health round-trip."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastmcp import Client

from btc_radar import server
from btc_radar.models.observation import RawObservation


def test_shape_strips_nulls_recursively():
    payload = {"a": 1, "b": None, "c": {"d": None, "e": 2}, "f": [1, None, {"g": None}]}
    assert server.shape(payload) == {"a": 1, "c": {"e": 2}, "f": [1, {}]}


def test_shape_truncation_meta():
    out = server.shape({"a": 1}, truncated=True)
    assert out["meta"]["truncated"] is True
    assert "guidance" in out["meta"]


def _http_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.invalid/x")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError("hata", request=req, response=resp)


@pytest.mark.parametrize(
    ("code", "beklenen"),
    [(429, "bekle"), (404, "sözleşmesi değişmiş"), (503, "tekrar dene"), (403, "erişim")],
)
def test_classify_http_errors_give_next_step(code, beklenen):
    err = server.classify_tool_error(_http_error(code), "binance_futures")
    assert beklenen in str(err)


def test_classify_value_error_no_stack_leak():
    err = server.classify_tool_error(ValueError("parse edilemedi: 'abc'"), "normalizer")
    assert "veri sözleşmesi ihlali" in str(err)
    assert "Traceback" not in str(err)


async def test_get_health_roundtrip():
    async with Client(server.app) as client:
        result = await client.call_tool("get_health", {})
    data = getattr(result, "data", None) or json.loads(result.content[0].text)
    assert data["status"] == "ok"
    assert data["config"]["weights_hash"]
    assert abs(sum(data["config"]["layers"].values()) - 1.0) < 1e-9
    assert data["providers"][0]["name"] == "binance_futures"
    assert data["providers"][0]["health"] == "not_polled"
    assert data["config"]["signal_rule_count"] == 2
    assert data["providers"][1]["name"] == "binance_futures_history"
    assert data["retrieved_at_utc"].endswith("+00:00")


async def test_get_derivatives_roundtrip_without_live_network(monkeypatch):
    class FakeProvider:
        name = "binance_futures"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def fetch(self, metric, **params):
            assert metric == "open_interest"
            assert params == {"symbol": "BTCUSDT"}
            observed = datetime(2026, 8, 3, 11, 59, tzinfo=UTC)
            return [
                RawObservation(
                    timestamp_utc=observed,
                    retrieved_at_utc=observed,
                    asset="BTC",
                    venue="binance_futures",
                    metric="open_interest",
                    raw_value=95_000.0,
                    unit="BTC",
                    source_group="derivatives",
                    source_url="https://fapi.binance.com/fapi/v1/openInterest",
                    quality=1.0,
                )
            ]

    monkeypatch.setattr(server, "BinanceFuturesProvider", FakeProvider)
    async with Client(server.app) as client:
        result = await client.call_tool("get_derivatives", {"metric": "open_interest"})
    data = getattr(result, "data", None) or json.loads(result.content[0].text)
    assert data["observations"][0]["metric"] == "open_interest"
    assert data["meta"]["scoring_available"] is False
    assert data["meta"]["scoring_blocker"] == "tool_returns_raw_observations_only"


async def test_health_says_collection_is_not_configured_when_no_store_is_set(monkeypatch):
    monkeypatch.delenv("BTC_RADAR_DB_PATH", raising=False)
    monkeypatch.delenv("BTC_RADAR_HEARTBEAT_DB_PATH", raising=False)

    async with Client(server.app) as client:
        result = await client.call_tool("get_health", {})
    data = getattr(result, "data", None) or json.loads(result.content[0].text)

    # Depo yokken "sağlıklı" demek, health aracının yapabileceği en kötü şeydir.
    assert data["collection"]["status"] == "not_configured"
    assert "healthy" not in data["collection"]


async def test_health_reports_collection_gaps_from_the_local_stores(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from btc_radar.core.heartbeat import HeartbeatStore
    from btc_radar.core.store import PointInTimeStore
    from btc_radar.models.observation import RawObservation

    now = datetime.now(UTC)
    pit_path = tmp_path / "pit.sqlite"
    heartbeat_path = tmp_path / "heartbeat.sqlite"

    with PointInTimeStore(pit_path) as store:
        store.append(
            [
                RawObservation(
                    timestamp_utc=now - timedelta(hours=offset),
                    retrieved_at_utc=now,
                    available_at_utc=now - timedelta(hours=offset) + timedelta(seconds=60),
                    asset="BTC",
                    venue="binance_futures",
                    metric="open_interest_value_1h",
                    raw_value=7_000_000_000.0,
                    unit="USDT",
                    window="1h",
                    source_group="derivatives",
                    source_url="https://fapi.binance.com/futures/data/openInterestHist",
                    quality=1.0,
                )
                for offset in range(1, 25)
            ],
            provider="binance_futures_history",
        )
    with HeartbeatStore(heartbeat_path) as heartbeat:
        heartbeat.record(
            task="collect",
            status="ok",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=5),
        )

    monkeypatch.setenv("BTC_RADAR_DB_PATH", str(pit_path))
    monkeypatch.setenv("BTC_RADAR_HEARTBEAT_DB_PATH", str(heartbeat_path))

    async with Client(server.app) as client:
        result = await client.call_tool("get_health", {})
    data = getattr(result, "data", None) or json.loads(result.content[0].text)

    collection = data["collection"]
    assert collection["status"] == "ok"
    tasks = {item["task"]: item for item in collection["tasks"]}
    assert tasks["collect"]["last_status"] == "ok"
    assert tasks["publish"]["runs"] == 0
    coverage = {item["metric"]: item for item in collection["coverage"]}
    assert coverage["open_interest_value_1h"]["observed_samples"] == 24
    # Funding hiç toplanmamış: tek bir metrik eksikken sistem sağlıklı sayılmaz.
    assert coverage["funding_rate_settled"]["observed_samples"] == 0
    assert collection["healthy"] is False


async def test_health_reports_an_unreadable_store_instead_of_failing(tmp_path, monkeypatch):
    broken = tmp_path / "pit.sqlite"
    broken.write_text("bu bir sqlite dosyası değil", encoding="utf-8")
    monkeypatch.setenv("BTC_RADAR_DB_PATH", str(broken))
    monkeypatch.delenv("BTC_RADAR_HEARTBEAT_DB_PATH", raising=False)

    async with Client(server.app) as client:
        result = await client.call_tool("get_health", {})
    data = getattr(result, "data", None) or json.loads(result.content[0].text)

    assert data["status"] == "ok"  # sunucu ayakta
    assert data["collection"]["status"] == "unreadable"  # ama veri katmanı arızalı
