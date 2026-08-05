"""Faz 2 Referans Taban Çizgisi (Baseline) Değerlendirici Testleri (ADR-0016)."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.baseline_evaluator import (
    evaluate_baseline_buy_and_hold,
    evaluate_baseline_cash,
    evaluate_baseline_simple_trend,
    evaluate_fold_baselines,
    evaluate_plan_baselines,
)
from scripts.baseline_evaluator import (
    main as cli_main,
)
from scripts.costslib import effective_fee, load_costs
from scripts.walk_forward_lib import (
    LockedOOSAccessError,
    generate_walk_forward_plan,
)


def _generate_synthetic_candles(start_iso: str, count: int, step_hours: int = 1) -> list[dict]:
    """Testler için timezone-aware UTC sentetik mum verisi üretir."""
    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(UTC)
    candles = []
    base_price = 50000.0

    for i in range(count):
        cur_dt = start_dt + timedelta(hours=i * step_hours)
        # Periodic price wave
        mult = 1.0 + 0.001 * (i % 10 - 5)
        price = base_price * mult
        candles.append(
            {
                "timestamp": cur_dt.isoformat().replace("+00:00", "Z"),
                "open": price,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price * 1.001,
            }
        )
    return candles


def test_100x_bit_identical_baseline_plan_output():
    """Aynı girdiyle 100 çalıştırmada %100 özdeş JSON çıktısı üretilmeli."""
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-06-01T00:00:00Z",
    )
    candles = _generate_synthetic_candles("2024-01-01T00:00:00Z", count=4000)

    ref_res = evaluate_plan_baselines(plan=plan, candles=candles)
    ref_json = json.dumps(ref_res, sort_keys=True)

    for _ in range(100):
        cur_res = evaluate_plan_baselines(plan=plan, candles=candles)
        cur_json = json.dumps(cur_res, sort_keys=True)
        assert cur_json == ref_json


def test_post_cost_deduction_buy_and_hold():
    """Buy & Hold taban çizgisinde komisyon ve kaymanın doğru düşüldüğünü doğrular."""
    costs = load_costs()
    scenario = "realistic"
    fee_oneside = effective_fee(costs, scenario)

    fold = {
        "fold_index": 0,
        "train_start_utc": "2024-01-01T00:00:00Z",
        "test_start_utc": "2024-04-01T00:00:00Z",
        "test_end_utc": "2024-05-01T00:00:00Z",
        "status": "valid",
    }

    # Price goes from 50,000 to 55,000 (+10% raw return)
    candles = [
        {
            "timestamp": "2024-04-01T00:00:00Z",
            "open": 50000.0,
            "high": 51000.0,
            "low": 49000.0,
            "close": 50500.0,
        },
        {
            "timestamp": "2024-04-30T23:00:00Z",
            "open": 54000.0,
            "high": 55500.0,
            "low": 53500.0,
            "close": 55000.0,
        },
    ]

    res = evaluate_baseline_buy_and_hold(fold, candles, costs, scenario, window_valid=True)
    assert res["status"] == "evaluated"
    assert res["raw_return"] == pytest.approx(0.10)
    assert res["effective_fee_oneside"] == fee_oneside

    # Net return must be strictly less than raw return due to fees
    assert res["net_return"] < res["raw_return"]

    expected_net = (1.0 + 0.10) * (1.0 - fee_oneside) / (1.0 + fee_oneside) - 1.0
    assert res["net_return"] == pytest.approx(expected_net)


def test_cash_baseline_semantics():
    """Cash taban çizgisinde net getiri = 0.0, fırsat maliyeti piyasa hareketi olmalı."""
    fold = {
        "fold_index": 0,
        "train_start_utc": "2024-01-01T00:00:00Z",
        "test_start_utc": "2024-04-01T00:00:00Z",
        "test_end_utc": "2024-05-01T00:00:00Z",
        "status": "valid",
    }
    candles = [
        {"timestamp": "2024-04-01T00:00:00Z", "open": 50000.0, "close": 50500.0},
        {"timestamp": "2024-04-30T23:00:00Z", "open": 54000.0, "close": 60000.0},
    ]

    res = evaluate_baseline_cash(fold, candles, window_valid=True)
    assert res["status"] == "evaluated"
    assert res["trade_count"] == 0
    assert res["raw_return"] == 0.0
    assert res["net_return"] == 0.0
    assert res["max_drawdown"] == 0.0
    assert res["opportunity_return"] == pytest.approx((60000.0 - 50000.0) / 50000.0)


def test_simple_trend_baseline_parameters_from_config():
    """Basit trend kontrolünde parametrelerin ve maliyetin doğru işlendiğini doğrular."""
    costs = load_costs()
    scenario = "realistic"
    trend_cfg = {"fast_period": 3, "slow_period": 5, "signal_mode": "long_short"}

    fold = {
        "fold_index": 0,
        "train_start_utc": "2024-01-01T00:00:00Z",
        "test_start_utc": "2024-01-01T05:00:00Z",
        "test_end_utc": "2024-01-01T10:00:00Z",
        "status": "valid",
    }

    # 10 candles with increasing/decreasing trend
    candles = _generate_synthetic_candles("2024-01-01T00:00:00Z", count=10, step_hours=1)

    res = evaluate_baseline_simple_trend(
        fold,
        test_candles=candles[5:],
        all_candles=candles,
        costs=costs,
        scenario=scenario,
        trend_cfg=trend_cfg,
        window_valid=True,
    )
    assert res["status"] == "evaluated"
    assert res["fast_period"] == 3
    assert res["slow_period"] == 5
    assert res["trade_count"] >= 0
    assert isinstance(res["net_return"], float)


def test_data_gap_or_empty_evaluated_as_unavailable():
    """Boş veya eksik veri durumunda sıfır getiri yerine unavailable/invalid dönmeli."""
    fold = {
        "fold_index": 0,
        "train_start_utc": "2024-01-01T00:00:00Z",
        "test_start_utc": "2024-04-01T00:00:00Z",
        "test_end_utc": "2024-05-01T00:00:00Z",
        "status": "invalid",
        "reason": "no_data_available",
    }

    res_fold = evaluate_fold_baselines(fold, candles=None)
    assert res_fold["data_status"] == "unavailable"

    baselines = res_fold["baselines"]
    for b_name in ("cash", "buy_and_hold", "simple_trend"):
        assert baselines[b_name]["net_return"] is None
        assert baselines[b_name]["raw_return"] is None
        assert baselines[b_name]["status"] in ("unavailable", "invalid")


def test_locked_oos_access_fails_closed_in_baselines():
    """Locked OOS dönemine erişen fold'lar varsayılan olarak reddedilmeli."""
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2026-09-01T00:00:00Z",
        allow_locked_oos=True,  # Plan has folds crossing locked OOS
    )
    # Force allow_locked_oos to False in plan parameters to test inheritance
    plan["parameters"]["allow_locked_oos"] = False

    with pytest.raises(LockedOOSAccessError, match="locked OOS"):
        evaluate_plan_baselines(plan=plan, candles=None)


def test_cli_baseline_evaluator_run(monkeypatch, capsys, tmp_path):
    """CLI run alt komutunu doğrular."""
    plan = generate_walk_forward_plan(
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-06-01T00:00:00Z",
    )
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "baseline_evaluator.py",
            "run",
            "--plan-file",
            str(plan_file),
        ],
    )
    cli_main()
    out = capsys.readouterr().out
    res_dict = json.loads(out)
    assert res_dict["protocol_version"] == "1.0"
    assert "evaluated_folds" in res_dict
    assert len(res_dict["evaluated_folds"]) > 0
