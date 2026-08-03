"""server.py sözleşme testleri: shape(), classify_tool_error(), get_health round-trip."""

import json

import httpx
import pytest
from fastmcp import Client

from btc_radar import server


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
    assert data["retrieved_at_utc"].endswith("+00:00")
