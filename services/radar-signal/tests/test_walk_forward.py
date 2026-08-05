"""Purged Walk-Forward + Embargo Protokolü Testleri (ADR-0014)."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.walk_forward import main as cli_main
from scripts.walk_forward_lib import (
    LockedOOSAccessError,
    ProtocolValidationError,
    evaluate_window_data,
    generate_walk_forward_plan,
    load_research_protocol_config,
    parse_utc_datetime,
    validate_split_plan,
)


def test_load_config_valid():
    cfg = load_research_protocol_config()
    assert cfg["version"] == "1.0"
    assert cfg["walk_forward"]["min_embargo_days"] >= 1
    assert "locked_oos_start_dt" in cfg["boundaries"]
    assert cfg["boundaries"]["locked_oos_start_dt"].tzinfo == UTC


def test_parse_utc_datetime():
    # Valid ISO strings with Z or +00:00
    dt1 = parse_utc_datetime("2024-01-01T00:00:00Z")
    assert dt1.tzinfo == UTC
    assert dt1.year == 2024

    dt2 = parse_utc_datetime("2024-01-01")
    assert dt2.tzinfo == UTC

    # Naive datetime must fail-loud
    naive_dt = datetime(2024, 1, 1, 0, 0, 0)
    with pytest.raises(ProtocolValidationError, match="Naive.*zaman damgası"):
        parse_utc_datetime(naive_dt)

    with pytest.raises(ProtocolValidationError, match="Geçersiz ISO"):
        parse_utc_datetime("invalid-date-string")


def test_100x_bit_identical_split_plan():
    """Aynı girdiden 100 kez %100 bit-identical split planı üretilmeli."""
    start = "2024-01-01T00:00:00Z"
    end = "2024-06-01T00:00:00Z"

    reference_plan = generate_walk_forward_plan(start_time=start, end_time=end)
    reference_json = json.dumps(reference_plan, sort_keys=True)

    for _ in range(100):
        plan = generate_walk_forward_plan(start_time=start, end_time=end)
        current_json = json.dumps(plan, sort_keys=True)
        assert current_json == reference_json


def test_purge_and_embargo_no_overlap():
    """Train/test arasında overlap olmamalı ve horizon purge edilmeli."""
    start = "2024-01-01T00:00:00Z"
    end = "2024-06-01T00:00:00Z"
    horizon_hours = 24
    embargo_days = 2

    plan = generate_walk_forward_plan(
        start_time=start,
        end_time=end,
        horizon_hours=horizon_hours,
        embargo_days=embargo_days,
    )
    assert validate_split_plan(plan)

    for fold in plan["folds"]:
        tr_raw_end = parse_utc_datetime(fold["train_raw_end_utc"])
        tr_purged_end = parse_utc_datetime(fold["train_purged_end_utc"])
        emb_start = parse_utc_datetime(fold["embargo_start_utc"])
        emb_end = parse_utc_datetime(fold["embargo_end_utc"])
        te_start = parse_utc_datetime(fold["test_start_utc"])
        te_end = parse_utc_datetime(fold["test_end_utc"])

        # Horizon purge check
        assert tr_raw_end - tr_purged_end == timedelta(hours=horizon_hours)
        assert tr_purged_end < tr_raw_end

        # Embargo check
        assert emb_start >= tr_raw_end
        assert (emb_end - emb_start).total_seconds() == embargo_days * 86400

        # No overlap check between train purged end and test start
        assert te_start >= emb_end
        assert te_start > tr_purged_end
        assert te_end > te_start


def test_embargo_below_minimum_fails_loud():
    """Config altındaki embargo süresi fail-loud reddedilmeli."""
    start = "2024-01-01T00:00:00Z"
    end = "2024-06-01T00:00:00Z"

    cfg = load_research_protocol_config()
    cfg["walk_forward"]["min_embargo_days"] = 2

    with pytest.raises(ProtocolValidationError, match="Embargo süresi"):
        generate_walk_forward_plan(start_time=start, end_time=end, embargo_days=1, config=cfg)


def test_locked_oos_access_fails_closed():
    """Varsayılan olarak Locked OOS dönemine erişim reddedilmeli."""
    start = "2024-01-01T00:00:00Z"
    end = "2026-08-10T00:00:00Z"  # Locked OOS is 2026-08-04

    with pytest.raises(LockedOOSAccessError, match="locked OOS"):
        generate_walk_forward_plan(start_time=start, end_time=end, allow_locked_oos=False)

    # Allowed only when explicitly requested
    plan = generate_walk_forward_plan(start_time=start, end_time=end, allow_locked_oos=True)
    assert len(plan["folds"]) > 0


def test_empty_or_insufficient_window_evaluated_as_unavailable_or_invalid():
    """Boş veya yetersiz pencere '0/nötr getiri' değil unavailable/invalid olmalı."""
    fold = {
        "fold_index": 0,
        "train_start_utc": "2024-01-01T00:00:00Z",
        "train_raw_end_utc": "2024-03-31T00:00:00Z",
        "train_purged_end_utc": "2024-03-30T00:00:00Z",
        "embargo_start_utc": "2024-03-31T00:00:00Z",
        "embargo_end_utc": "2024-04-01T00:00:00Z",
        "test_start_utc": "2024-04-01T00:00:00Z",
        "test_end_utc": "2024-05-01T00:00:00Z",
        "status": "valid",
    }

    # Case 1: None or empty data
    res_none = evaluate_window_data(fold, candles=None)
    assert res_none["status"] == "unavailable"

    res_empty = evaluate_window_data(fold, candles=[])
    assert res_empty["status"] == "unavailable"

    # Case 2: Insufficient candles (<100)
    few_candles = [{"timestamp": 1704067200000 + i * 3600000} for i in range(10)]
    res_few = evaluate_window_data(fold, candles=few_candles)
    assert res_few["status"] == "invalid"
    assert "insufficient_candles" in res_few["reason"]

    # Case 3: Data gap exceeded (>3600s)
    gap_candles = [{"timestamp": 1704067200000}]
    gap_candles.extend([{"timestamp": 1704067200000 + 7200000 + i * 3600000} for i in range(150)])
    res_gap = evaluate_window_data(fold, candles=gap_candles)
    assert res_gap["status"] == "invalid"
    assert "data_gap_exceeded" in res_gap["reason"]


def test_cli_generate_and_validate_plan(monkeypatch, capsys, tmp_path):
    """CLI generate-plan, validate-plan ve evaluate-windows komutlarını doğrular."""
    # 1. generate-plan
    monkeypatch.setattr(
        "sys.argv",
        [
            "walk_forward.py",
            "generate-plan",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2024-06-01T00:00:00Z",
        ],
    )
    cli_main()
    out = capsys.readouterr().out
    plan_dict = json.loads(out)
    assert plan_dict["protocol_version"] == "1.0"
    assert len(plan_dict["folds"]) > 0

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(out, encoding="utf-8")

    # 2. validate-plan
    monkeypatch.setattr(
        "sys.argv",
        [
            "walk_forward.py",
            "validate-plan",
            "--plan-file",
            str(plan_file),
        ],
    )
    cli_main()
    out2 = capsys.readouterr().out
    assert '"valid": true' in out2

    # 3. evaluate-windows without data -> fail closed (unavailable)
    monkeypatch.setattr(
        "sys.argv",
        [
            "walk_forward.py",
            "evaluate-windows",
            "--plan-file",
            str(plan_file),
        ],
    )
    cli_main()
    out3 = capsys.readouterr().out
    eval_dict = json.loads(out3)
    assert eval_dict["folds"][0]["status"] == "unavailable"


def test_cli_locked_oos_fails_closed(monkeypatch, capsys):
    """CLI varsayılan olarak Locked OOS dönemini açmaya çalıştığında exit code 1 dönmeli."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "walk_forward.py",
            "generate-plan",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2026-08-10T00:00:00Z",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 1
    err_out = capsys.readouterr().err
    assert "locked OOS" in err_out
