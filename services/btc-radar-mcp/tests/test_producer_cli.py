import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from btc_radar.core.heartbeat import HeartbeatStore
from btc_radar.core.runlock import exclusive_run_lock
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
SPOT_FIXTURES = Path(__file__).parent / "fixtures" / "binance_spot"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _spot_fixture(name: str):
    return json.loads((SPOT_FIXTURES / name).read_text(encoding="utf-8"))


def _closed_hour_klines_payload() -> list:
    """One always-closed candle for the PREVIOUS UTC hour, computed relative to real time.

    `producer._collect` uses the real system clock (no injected clock), so a fixture
    fixed to a past calendar date would eventually be seen as "the still-open candle"
    once wall-clock time moves past it. Anchoring to "now - 1h" keeps the fixture valid
    no matter when the test actually runs.
    """
    hour_start = (datetime.now(UTC) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    open_ms = int(hour_start.timestamp() * 1000)
    close_ms = int((hour_start + timedelta(hours=1)).timestamp() * 1000) - 1
    return [
        [
            open_ms,
            "64233.35000000",
            "64420.00000000",
            "64001.68000000",
            "64341.00000000",
            "558.35238000",
            close_ms,
            "35853995.31908820",
            96909,
            "284.87500000",
            "18292658.93393350",
            "0",
        ]
    ]


def _mock_order_book_and_spot() -> None:
    respx.get("https://fapi.binance.com/fapi/v1/depth").mock(
        return_value=httpx.Response(200, json=_fixture("depth_btcusdt.json"))
    )
    respx.get("https://api.binance.com/api/v3/klines").mock(
        return_value=httpx.Response(200, json=_closed_hour_klines_payload())
    )
    respx.get("https://api.binance.com/api/v3/ticker/price").mock(
        return_value=httpx.Response(200, json=_spot_fixture("ticker_price_btcusdt.json"))
    )


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
    _mock_order_book_and_spot()

    main(["collect", "--pit-db", str(tmp_path / "pit.sqlite"), "--history-limit", "3"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"] == ["funding_rate", "mark_price", "open_interest"]
    assert payload["order_book"]["metrics"] == [
        "order_book_depth_ask_usd",
        "order_book_depth_bid_usd",
        "order_book_spread_bps",
    ]
    assert payload["spot"]["metrics"] == [
        "spot_close",
        "spot_high",
        "spot_low",
        "spot_open",
        "spot_perp_basis",
        "spot_volume",
    ]
    history = {item["metric"]: item for item in payload["history"]}
    assert set(history) == {"funding_rate_settled", "open_interest_1h"}
    assert history["funding_rate_settled"]["inserted"] == 12
    # 48 saatlik kova × 2 metrik (kontrat + notional)
    assert history["open_interest_1h"]["inserted"] == 96
    assert payload["rows_total"] == 3 + 3 + 6 + 12 + 96


@respx.mock
def test_collect_cli_can_skip_history(tmp_path, capsys):
    respx.get("https://fapi.binance.com/fapi/v1/premiumIndex").mock(
        return_value=httpx.Response(200, json=_fixture("premium_index_btcusdt.json"))
    )
    respx.get("https://fapi.binance.com/fapi/v1/openInterest").mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )
    _mock_order_book_and_spot()

    main(["collect", "--pit-db", str(tmp_path / "pit.sqlite"), "--history-limit", "0"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["history"] == []
    assert payload["rows_total"] == 3 + 3 + 6


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


def _mock_public_endpoints() -> None:
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
    _mock_order_book_and_spot()


def _run_args(tmp_path, *extra: str) -> list[str]:
    return [
        "run",
        "--pit-db",
        str(tmp_path / "pit.sqlite"),
        "--snapshot-db",
        str(tmp_path / "snapshots.sqlite"),
        "--heartbeat-db",
        str(tmp_path / "heartbeat.sqlite"),
        "--context-root",
        str(tmp_path / "context"),
        *extra,
    ]


@respx.mock
def test_run_single_tick_collects_publishes_and_leaves_a_heartbeat(tmp_path, capsys):
    _mock_public_endpoints()

    main(_run_args(tmp_path))

    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [(item["task"], item["status"]) for item in lines] == [
        ("collect", "ok"),
        ("publish", "ok"),
    ]
    assert all(item["invocation"] == "single_tick" for item in lines)
    assert (tmp_path / "heartbeat.sqlite").is_file()

    with HeartbeatStore(tmp_path / "heartbeat.sqlite") as heartbeat:
        assert heartbeat.last_success("collect") is not None
        assert heartbeat.latest_success_as_of("publish") is not None


@respx.mock
def test_second_tick_does_not_republish_the_same_hour(tmp_path, capsys):
    _mock_public_endpoints()

    main(_run_args(tmp_path))
    capsys.readouterr()
    main(_run_args(tmp_path))

    output = capsys.readouterr().out.strip()
    tasks = [json.loads(line)["task"] for line in output.splitlines()] if output else []
    assert "publish" not in tasks  # aynı saat değişmez; ikinci kez yayınlanmaz


@respx.mock
def test_run_records_a_failing_endpoint_instead_of_crashing(tmp_path, capsys):
    respx.get("https://fapi.binance.com/fapi/v1/premiumIndex").mock(
        return_value=httpx.Response(503, json={"msg": "service unavailable"})
    )
    respx.get("https://fapi.binance.com/fapi/v1/openInterest").mock(
        return_value=httpx.Response(200, json=_fixture("open_interest_btcusdt.json"))
    )

    main(_run_args(tmp_path))

    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    collect = next(item for item in lines if item["task"] == "collect")
    assert collect["status"] == "error"
    assert collect["consecutive_failures"] == 1
    # Toplama düşse de kapanan saat için fail-closed context yine yayınlanır.
    assert next(item for item in lines if item["task"] == "publish")["status"] == "ok"


@respx.mock
def test_run_refuses_to_start_next_to_a_held_lock(tmp_path, capsys):
    _mock_public_endpoints()
    lock = tmp_path / "producer.lock"

    with exclusive_run_lock(lock):
        exit_code = main(_run_args(tmp_path, "--lock-file", str(lock)))

    # Ham traceback değil, makine-okunur hata kaydı ve sıfırdan farklı çıkış kodu.
    assert exit_code == 2
    error = json.loads(capsys.readouterr().err.strip())
    assert error["error_type"] == "RunLockError"
    assert "zaten tutuluyor" in error["error"]


def test_run_requires_a_context_root(tmp_path, monkeypatch):
    monkeypatch.delenv("BTC_RADAR_CONTEXT_ROOT", raising=False)
    with pytest.raises(SystemExit):
        main(["run", "--pit-db", str(tmp_path / "pit.sqlite")])


@respx.mock
def test_status_reports_heartbeat_and_data_coverage(tmp_path, capsys):
    _mock_public_endpoints()
    main(_run_args(tmp_path))
    capsys.readouterr()

    main(
        [
            "status",
            "--pit-db",
            str(tmp_path / "pit.sqlite"),
            "--heartbeat-db",
            str(tmp_path / "heartbeat.sqlite"),
            "--window-days",
            "2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    tasks = {item["task"]: item for item in payload["tasks"]}
    assert tasks["collect"]["last_status"] == "ok"
    assert tasks["publish"]["consecutive_failures"] == 0
    assert payload["publish"]["hours_behind"] == 0
    coverage = {item["metric"]: item for item in payload["coverage"]}
    assert set(coverage) == {"funding_rate_settled", "open_interest_value_1h"}
    # Tolerans raporda uydurulmaz; feature kapısıyla aynı config'ten gelir.
    assert coverage["funding_rate_settled"]["tolerated_gap_seconds"] == 43200.0
    assert coverage["open_interest_value_1h"]["tolerated_gap_seconds"] == 10800.0
    # Sağlık, duvar saatine göre değişen bir gözlemdir; testin sabitlediği şey raporun
    # bunu her metrik için ayrı ayrı ve gerekçeleriyle vermesidir.
    assert payload["healthy"] == all(item["healthy"] for item in payload["coverage"])
    assert all("longest_gap_start_at" in item for item in payload["coverage"])
