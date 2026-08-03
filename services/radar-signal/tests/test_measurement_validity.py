"""ADIM 2 — Ölçüm geçerliliği ve sermaye tükenmesi kontrolü birim testleri (DoD-1)."""

from datetime import UTC, datetime

import pytest
from measurement_validity import calculate_expectancy, check_capital_depletion


def test_check_capital_depletion_normal():
    is_depleted, reason = check_capital_depletion(
        last_trade_date=datetime(2026, 2, 2, tzinfo=UTC),
        timerange_end=datetime(2026, 2, 3, tzinfo=UTC),
        final_balance=9500.0,
        starting_balance=10000.0,
    )
    assert not is_depleted
    assert reason == "OK"


def test_check_capital_depletion_triggered():
    is_depleted, reason = check_capital_depletion(
        last_trade_date="2025-03-12T16:43:00+00:00",
        timerange_end="2026-02-03T00:00:00+00:00",
        final_balance=1006.0,
        starting_balance=10000.0,
    )
    assert is_depleted
    assert "GEÇERSİZ — sermaye tükendi" in reason


def test_calculate_expectancy_empty():
    res = calculate_expectancy([])
    assert res["count"] == 0
    assert res["net_expectancy_pct"] == 0.0


def test_calculate_expectancy_values():
    trades = [
        {"profit_ratio": 0.02},
        {"profit_ratio": -0.01},
        {"profit_ratio": -0.005},
    ]
    res = calculate_expectancy(trades)
    assert res["count"] == 3
    assert res["net_expectancy_pct"] == pytest.approx(0.1667, abs=0.001)
    assert res["net_expectancy_bps"] == pytest.approx(16.67, abs=0.1)
