import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.producer import _parse_as_of, main


def test_parse_as_of_requires_exact_utc_hour():
    assert _parse_as_of("2026-08-03T12:00:00Z") == datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    with pytest.raises(Exception, match="1h sınırı"):
        _parse_as_of("2026-08-03T12:15:00Z")


def test_publish_cli_creates_fail_closed_artifact(tmp_path, capsys):
    pit = tmp_path / "pit.sqlite"
    snapshots = tmp_path / "snapshots.sqlite"
    context_root = tmp_path / "context"

    main(
        [
            "publish",
            "--as-of",
            "2026-08-03T12:00:00Z",
            "--pit-db",
            str(pit),
            "--snapshot-db",
            str(snapshots),
            "--context-root",
            str(context_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "created"
    assert payload["rows_considered"] == 0
    assert payload["directional_decision_allowed"] is False
    assert payload["direction"] is None
    assert (context_root / "v1/BTCUSDT/1h/2026/08/03/12.json").is_file()


def test_publish_cli_requires_context_root(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "publish",
                "--as-of",
                "2026-08-03T12:00:00Z",
                "--pit-db",
                str(tmp_path / "pit.sqlite"),
                "--snapshot-db",
                str(tmp_path / "snapshots.sqlite"),
            ]
        )


FIXTURES = Path(__file__).parent / "fixtures" / "binance_usdm"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
def test_collect_cli_stores_both_the_snapshot_and_the_newest_history(tmp_path, capsys):
    respx.get("https://fapi.binance.com/fapi/v1/premiumIndex").mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/fapi/v1/openInterest").mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/fapi/v1/fundingRate").mock(
        return_value=httpx.Response(200, json=_fixture("funding_rate_history_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/futures/data/openInterestHist").mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_hist_1h_btcusdt.json"))
    )

    main(["collect", "--pit-db", str(tmp_path / "pit.sqlite"), "--history-limit", "3"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"] == ["funding_rate", "mark_price", "open_interest"]
    history = {item["metric"]: item for item in payload["history"]}
    assert set(history) == {"funding_rate_settled", "open_interest_1h"}
    assert history["funding_rate_settled"]["inserted"] == 12
    # 48 saatlik kova × 2 metrik (kontrat + notional)
    assert history["open_interest_1h"]["inserted"] == 96
    assert payload["rows_total"] == 3 + 12 + 96


@respx.mock
def test_collect_cli_can_skip_history(tmp_path, capsys):
    respx.get("https://fapi.binance.com/fapi/v1/premiumIndex").mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/fapi/v1/openInterest").mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )

    main(["collect", "--pit-db", str(tmp_path / "pit.sqlite"), "--history-limit", "0"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["history"] == []
    assert payload["rows_total"] == 3


@respx.mock
def test_backfill_cli_reports_stored_history_not_requested_history(tmp_path, capsys):
    respx.get("https://fapi.binance.com/fapi/v1/fundingRate").mock(
        return_value=httpx.Response(200, json=_fixture("funding_rate_history_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/futures/data/openInterestHist").mock(
        return_value=httpx.Response(
            400, json={"code": -1130, "msg": "parameter 'startTime' is invalid."}
        )
    )

    main(
        [
            "backfill",
            "--pit-db",
            str(tmp_path / "pit.sqlite"),
            "--funding-days",
            "4",
            "--open-interest-days",
            "30",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    results = {item["metric"]: item for item in payload["results"]}
    assert results["funding_rate_settled"]["inserted"] == 12
    assert results["funding_rate_settled"]["max_gap_seconds"] == pytest.approx(28800.0, abs=1.0)
    # Borsa saklama sınırına çarptı: sessiz "veri yok" değil, açık bir kısıtlama raporu.
    assert results["open_interest_1h"]["inserted"] == 0
    assert results["open_interest_1h"]["truncated_reason"] == "exchange_retention"


def test_backfill_cli_rejects_non_positive_days(tmp_path):
    with pytest.raises(SystemExit):
        main(["backfill", "--pit-db", str(tmp_path / "pit.sqlite"), "--funding-days", "0"])
