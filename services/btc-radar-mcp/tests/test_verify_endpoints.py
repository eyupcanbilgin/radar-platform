"""Smoke script: coğrafi engel ile sözleşme kırılması ayrı durumlardır (ADR-0009).

Ağa çıkılmaz; `httpx.MockTransport` ile yanıtlar sahnelenir (CLAUDE.md: canlı API'ye
giden test yazma).
"""

import importlib.util
from pathlib import Path

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_endpoints.py"
_spec = importlib.util.spec_from_file_location("verify_endpoints", _SCRIPT)
assert _spec and _spec.loader
ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve)

# GitHub-hosted runner'da gözlenen gerçek gövde (koşu 30894903581, kısaltılmış).
CLOUDFRONT_BODY = (
    "<HTML><HEAD><TITLE>ERROR: The request could not be satisfied</TITLE></HEAD><BODY>"
    "<H1>403 ERROR</H1><H2>The request could not be satisfied.</H2>"
    "The Amazon CloudFront distribution is configured to block access from your country."
    "</BODY></HTML>"
)
# Binance'in kendi kısıtlı-bölge yanıtı.
BINANCE_451_BODY = (
    '{"code":0,"msg":"Service unavailable from a restricted location according to '
    "'b. Eligibility' in https://www.binance.com/en/terms\"}"
)


def _check(check_id: str) -> ve.Check:
    for chk in ve.CHECKS:
        if chk.check_id == check_id:
            return chk
    raise AssertionError(f"{check_id} CHECKS içinde yok")


async def _run(chk: ve.Check, *, status: int, body: str, headers: dict | None = None) -> ve.Result:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers=headers)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await ve.run_check(client, chk)


# ── geo_block_reason: iki koşul birden aranır


def test_cloudfront_403_is_a_geo_block():
    assert ve.geo_block_reason(403, CLOUDFRONT_BODY) is not None


def test_binance_451_is_a_geo_block():
    assert ve.geo_block_reason(451, BINANCE_451_BODY) is not None


def test_plain_403_is_not_a_geo_block():
    """İşaretsiz 403, kaldırılmış uç veya değişmiş imza da olabilir — yutulmaz."""
    assert ve.geo_block_reason(403, '{"code":-1022,"msg":"Signature invalid"}') is None


def test_geo_marker_on_success_status_is_not_a_block():
    assert ve.geo_block_reason(200, CLOUDFRONT_BODY) is None


# ── run_check: engel ayrı bir durum, zorunlu FAIL değil


async def test_blocked_check_reports_blocked_state():
    result = await _run(_check("binance_oi"), status=403, body=CLOUDFRONT_BODY)
    assert result.blocked is True
    assert result.ok is False
    assert result.state == "blocked"
    assert "ortam engeli" in result.detail


async def test_geo_block_does_not_satisfy_expect_failure():
    """`allForceOrders` kaldırıldı varsayımı, coğrafi 403 ile DOĞRULANMIŞ sayılamaz."""
    result = await _run(_check("binance_forceorders_removed"), status=403, body=CLOUDFRONT_BODY)
    assert result.state == "blocked"
    assert result.ok is False


async def test_expect_failure_still_passes_on_a_real_removal():
    result = await _run(
        _check("binance_forceorders_removed"),
        status=404,
        body='{"code":-1121,"msg":"Invalid symbol."}',
    )
    assert result.state == "ok"
    assert result.blocked is False


async def test_unmarked_403_remains_a_required_failure():
    result = await _run(_check("binance_oi"), status=403, body="Forbidden by WAF")
    assert result.state == "fail"
    assert result.blocked is False


async def test_contract_break_on_200_still_fails():
    result = await _run(_check("binance_oi"), status=200, body='{"symbol":"BTCUSDT"}')
    assert result.state == "fail"
    assert "eksik alan" in result.detail


# ── render: engel ayrı sayılır ve adıyla yazılır


def _result(check_id: str, **kwargs) -> ve.Result:
    base = {"ok": False, "required": True}
    base.update(kwargs)
    return ve.Result(check_id, "derivatives", "SPEC:43", "https://example.invalid", **base)


def test_render_does_not_count_blocked_as_required_failure():
    report, fails, blocked = ve.render(
        [
            _result("binance_oi", blocked=True, status=403),
            _result("bybit_oi", ok=True),
        ]
    )
    assert fails == 0
    assert blocked == 1
    assert "1 blocked_in_environment" in report


def test_render_names_the_unverified_checks():
    report, _, _ = ve.render([_result("binance_oi", blocked=True, status=403)])
    assert "blocked_in_environment" in report
    assert "binance_oi (403)" in report
    assert "--fail-on-blocked" in report


def test_render_still_counts_genuine_failures_alongside_blocks():
    report, fails, blocked = ve.render(
        [
            _result("binance_oi", blocked=True, status=403),
            _result("cbbi_latest", detail="alan yok"),
            _result("fx_erapi", required=False),
        ]
    )
    assert (fails, blocked) == (1, 1)
    assert "| FAIL | cbbi_latest" in report
    assert "| warn | fx_erapi" in report


@pytest.mark.parametrize(
    ("fails", "blocked", "fail_on_blocked", "expected"),
    [(0, 0, False, 0), (0, 2, False, 0), (0, 2, True, 2), (1, 2, False, 1), (1, 0, True, 1)],
)
def test_exit_code_policy(fails: int, blocked: int, fail_on_blocked: bool, expected: int):
    """Engellenmiş-ama-erişilebilir 0; gerçek sözleşme kırılması her hâlükârda 1."""
    assert ve.exit_code(fails, blocked, fail_on_blocked) == expected
