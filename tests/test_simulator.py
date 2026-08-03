"""Mum-içi simülatör testleri (CR-002 P0-5): belirsizlik aleyhimize çözülür."""

import pytest
from simlib import Candle, is_ambiguous, resolve_intracandle, slippage_bps

from costslib import load_costs


# --- Long kurulum ----------------------------------------------------------------------
def test_long_only_target_hit():
    assert resolve_intracandle(Candle(high=105, low=99), stop=95, target=104) == "TARGET"


def test_long_only_stop_hit():
    assert resolve_intracandle(Candle(high=101, low=94), stop=95, target=110) == "STOP"


def test_long_both_hit_stop_wins():
    """KURAL: aynı 1m mumda hem stop hem hedef görüldüyse STOP önce sayılır."""
    both = Candle(high=110, low=94)
    assert is_ambiguous(both, stop=95, target=105) is True
    assert resolve_intracandle(both, stop=95, target=105) == "STOP"


def test_long_neither_hit():
    assert resolve_intracandle(Candle(high=104, low=96), stop=95, target=105) == "NONE"


def test_long_touch_is_hit_not_miss():
    """Seviyeye tam dokunuş 'gerçekleşti' sayılır (muhafazakâr taraf)."""
    assert resolve_intracandle(Candle(high=104, low=95), stop=95, target=105) == "STOP"
    assert resolve_intracandle(Candle(high=105, low=96), stop=95, target=105) == "TARGET"


# --- Short kurulum ---------------------------------------------------------------------
def test_short_only_target_hit():
    assert resolve_intracandle(Candle(high=104, low=95), stop=110, target=96, is_short=True) == (
        "TARGET"
    )


def test_short_both_hit_stop_wins():
    both = Candle(high=111, low=94)
    assert is_ambiguous(both, stop=110, target=95, is_short=True) is True
    assert resolve_intracandle(both, stop=110, target=95, is_short=True) == "STOP"


# --- Fail-loud girdi doğrulaması -------------------------------------------------------
def test_invalid_candle_rejected():
    with pytest.raises(ValueError, match="geçersiz mum"):
        Candle(high=90, low=100)


def test_long_with_stop_above_target_rejected():
    with pytest.raises(ValueError, match="long kurulumda"):
        resolve_intracandle(Candle(high=110, low=90), stop=105, target=95)


def test_short_with_stop_below_target_rejected():
    with pytest.raises(ValueError, match="short kurulumda"):
        resolve_intracandle(Candle(high=110, low=90), stop=95, target=105, is_short=True)


# --- Dinamik kayma (rejime bağlı) ------------------------------------------------------
def test_slippage_uses_scenario_when_calm():
    costs = load_costs()
    assert slippage_bps(20.0, costs, scenario="realistic") == 4.0


def test_slippage_escalates_when_fragile():
    """Kırılganlık ≥60 → stres bps (18), rejim-körü 4 bps değil."""
    costs = load_costs()
    assert slippage_bps(60.0, costs, scenario="realistic") == 18.0
    assert slippage_bps(85.0, costs, scenario="realistic") == 18.0


def test_stress_never_softens_a_harsher_scenario():
    costs = load_costs()
    assert slippage_bps(90.0, costs, scenario="cascade") == 60.0  # 18'e düşmez


def test_unknown_fragility_uses_base_not_invented_penalty():
    costs = load_costs()
    assert slippage_bps(None, costs, scenario="realistic") == 4.0


def test_unknown_scenario_fails_loud():
    with pytest.raises(ValueError, match="tanımsız senaryo"):
        slippage_bps(10.0, load_costs(), scenario="bedava")
