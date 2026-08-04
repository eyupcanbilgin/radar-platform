"""Boyutlandırma testleri (Ç6): oran config'den gelir, sabit notional tuzağı kapalı."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from sizinglib import load_sizing, wallet_pct_stake  # noqa: E402


@pytest.fixture
def sizing():
    return load_sizing()


def test_config_loads_and_is_sane(sizing):
    assert 0 < sizing["stake_pct_of_wallet"] <= 1.0
    assert sizing["min_stake_fallback"] > 0


def test_stake_scales_with_wallet(sizing):
    """ASIL KORUMA: cüzdan düşerken bahis de düşmeli (sabit notional tavanlanmaya yol açtı)."""
    assert wallet_pct_stake(10000, None, sizing) == pytest.approx(1000.0)
    assert wallet_pct_stake(5000, None, sizing) == pytest.approx(500.0)
    assert wallet_pct_stake(2000, None, sizing) == pytest.approx(200.0)


def test_ratio_of_stake_to_wallet_is_constant(sizing):
    """Sabit notional'da bu oran cüzdan düştükçe büyüyordu; artık sabit kalmalı."""
    ratios = [wallet_pct_stake(w, None, sizing) / w for w in (10000, 5000, 2500, 1250)]
    assert len(set(round(r, 10) for r in ratios)) == 1


def test_min_stake_is_respected(sizing):
    """Borsa min_stake'i altına inilmez (yüzde çok küçük kalsa bile)."""
    assert wallet_pct_stake(50, 25.0, sizing) == 25.0
    assert wallet_pct_stake(1000, 25.0, sizing) == pytest.approx(100.0)


def test_fallback_floor_when_exchange_min_unknown(sizing):
    assert wallet_pct_stake(1.0, None, sizing) == sizing["min_stake_fallback"]


def test_negative_wallet_fails_loud(sizing):
    with pytest.raises(ValueError, match="negatif"):
        wallet_pct_stake(-1, None, sizing)


@pytest.mark.parametrize("bad", ["0", "1.5", "-0.1"])
def test_invalid_ratio_fails_loud(tmp_path, bad):
    p = tmp_path / "sizing.yaml"
    p.write_text(f"version: '1'\nstake_pct_of_wallet: {bad}\nmin_stake_fallback: 10\n", "utf-8")
    with pytest.raises(ValueError, match="stake_pct_of_wallet"):
        load_sizing(p)


def test_invalid_floor_fails_loud(tmp_path):
    p = tmp_path / "sizing.yaml"
    p.write_text("version: '1'\nstake_pct_of_wallet: 0.1\nmin_stake_fallback: 0\n", "utf-8")
    with pytest.raises(ValueError, match="min_stake_fallback"):
        load_sizing(p)
