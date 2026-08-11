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


# --- ADR-0013: kanıt kütüğü — engelli koşu kanıt değildir -----------------------------

RUN_AT = "2026-08-11T12:00:00+00:00"


def _entry(results, *, full_scope: bool = True) -> str:
    return ve.evidence_entry(results, run_at=RUN_AT, commit="abc1234", full_scope=full_scope)


def test_a_blocked_run_is_refused_as_evidence():
    """CI'nın her gün ürettiği koşu tam olarak budur; kütüğe girerse kütük anlamını yitirir."""
    with pytest.raises(ve.EvidenceRefused) as exc:
        _entry([_result("bybit_oi", ok=True), _result("binance_oi", blocked=True, status=451)])

    assert "binance_oi" in str(exc.value)


def test_a_run_with_a_broken_contract_is_refused_as_evidence():
    with pytest.raises(ve.EvidenceRefused) as exc:
        _entry([_result("bybit_oi", ok=True), _result("cbbi_latest", detail="alan yok")])

    assert "cbbi_latest" in str(exc.value)


def test_a_clean_unblocked_run_is_recorded_with_its_scope():
    entry = _entry([_result("binance_oi", ok=True, status=200)], full_scope=False)

    assert RUN_AT in entry
    assert "abc1234" in entry
    assert "bitcoin-data hariç" in entry
    assert "| binance_oi | 200 | SPEC:43 |" in entry


def test_informational_failures_stay_visible_instead_of_reading_as_all_verified():
    """warn kaydı engellemez; ama girdi 'hepsi doğrulandı' diye okunmamalı."""
    entry = _entry(
        [
            _result("binance_oi", ok=True, status=200),
            _result("fx_erapi", required=False, status=500),
        ]
    )

    assert "1 warn" in entry
    assert "fx_erapi (500)" in entry


def test_no_raw_market_data_reaches_the_log():
    """Platform kural 2: ham piyasa verisi Git'e girmez; yanıt gövdesi kaydedilmez."""
    entry = _entry([_result("binance_oi", ok=True, status=200, sample={"openInterest": "105951"})])

    assert "105951" not in entry
    assert "openInterest" not in entry


def test_recording_appends_and_never_rewrites_earlier_entries(tmp_path):
    log = tmp_path / "kanit.md"
    ve.record_evidence(
        [_result("binance_oi", ok=True, status=200)],
        str(log),
        run_at="2026-08-01T00:00:00+00:00",
        commit="0000001",
        full_scope=True,
    )
    first = log.read_text(encoding="utf-8")

    ve.record_evidence(
        [_result("bybit_oi", ok=True, status=200)],
        str(log),
        run_at=RUN_AT,
        commit="abc1234",
        full_scope=True,
    )
    second = log.read_text(encoding="utf-8")

    assert second.startswith(first)  # geçmiş girdi bit-bit korunuyor
    assert "0000001" in second and "abc1234" in second
    assert second.count("# Endpoint doğrulama kanıt kütüğü") == 1


def test_a_refused_run_leaves_no_trace_in_the_log(tmp_path):
    log = tmp_path / "kanit.md"
    with pytest.raises(ve.EvidenceRefused):
        ve.record_evidence(
            [_result("binance_oi", blocked=True, status=451)],
            str(log),
            run_at=RUN_AT,
            commit="abc1234",
            full_scope=True,
        )

    assert not log.exists()
