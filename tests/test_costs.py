"""costs.yaml sözleşme testleri (CR-5): fail-loud yükleme + senaryo matematiği."""

from pathlib import Path

import pytest

from costslib import costs_hash, effective_fee, load_costs


def test_costs_load_ok():
    c = load_costs()
    assert c["version"] == "1.0"
    assert c["funding"]["mode"] == "historical"
    assert c["slippage_oneway"]["BTCUSDT"] == 0.0002


def test_effective_fee_realistic():
    c = load_costs()
    # taker 0.00045 + 4 bps kayma = 0.00085 tek yön
    assert effective_fee(c, "realistic") == pytest.approx(0.00085)


def test_effective_fee_cascade_is_heaviest():
    c = load_costs()
    fees = [effective_fee(c, s) for s in
            ("optimistic_maker", "realistic", "taker_heavy", "stressed", "cascade")]
    assert fees == sorted(fees)
    assert fees[-1] == pytest.approx(0.00045 + 0.006)


def test_unknown_scenario_fails_loud():
    c = load_costs()
    with pytest.raises(ValueError, match="tanımsız senaryo"):
        effective_fee(c, "bedava")


def test_broken_costs_fails_loud(tmp_path: Path):
    bad = tmp_path / "costs.yaml"
    bad.write_text("version: '1'\nfees:\n  taker: 0.5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_costs(bad)


def test_costs_hash_stable():
    assert costs_hash() == costs_hash()
    assert len(costs_hash()) == 12
