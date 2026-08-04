"""Nabız analizi testleri — ölçüm aracının kendisi ve yeni modları doğru mu?

Bu script hipotez kapatma ve eleme yetkisi taşıdığından (ADR-0006), yönsel getiri
ve volatilite oranı modlarının pozitif/negatif/sıfır kontrollerinde bilinen
cevabı bulduğu kanıtlanmalıdır.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from signal_pulse import (  # noqa: E402
    HORIZONS,
    benjamini_hochberg,
    build_signals_card_a,
    load_fomc_calendar,
    permutation_test,
)


def _frame(n: int = 4000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": rng.lognormal(3, 0.5, n),
            "funding_rate": np.zeros(n),
        }
    )


def test_forward_returns_are_actually_forward():
    d = build_signals_card_a(_frame(), window=80)
    row = 500
    for h in HORIZONS:
        expected = d["close"].iloc[row + h] / d["close"].iloc[row] - 1.0
        assert d[f"fwd_{h}"].iloc[row] == pytest.approx(expected)


def test_last_bars_have_no_forward_return():
    """Serinin sonunda ileri getiri tanımsız olmalı — uydurulmamalı."""
    d = build_signals_card_a(_frame(), window=80)
    assert d["fwd_16"].iloc[-1] != d["fwd_16"].iloc[-1]  # NaN


def test_permutation_detects_real_positive_edge():
    """POZİTİF KONTROL: gerçek yönsel avantaj varsa test onu bulmalı."""
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(0.004, 0.01, 800)  # +40 bps gerçek avantaj
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="directional")
    assert res["p_greater"] < 0.01
    assert res["p_less"] > 0.99


def test_permutation_detects_real_negative_edge():
    """NEGATİF KONTROL: Kart A'da bulunan yön — anlamlı KÖTÜ tespit edilmeli."""
    rng = np.random.default_rng(2)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(-0.004, 0.01, 800)
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="directional")
    assert res["p_less"] < 0.01


def test_permutation_finds_nothing_when_there_is_nothing():
    """SIFIR KONTROLÜ: avantaj yoksa p değerleri uçlarda olmamalı."""
    rng = np.random.default_rng(3)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(0, 0.01, 800)
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="directional")
    assert 0.02 < res["p_greater"] < 0.98
    assert 0.02 < res["p_less"] < 0.98


def test_volatility_ratio_permutation_detects_real_expansion():
    """POZİTİF KONTROL (Volatilite Modu): Gerçek volatilite genişlemesi tespit edilmeli."""
    rng = np.random.default_rng(4)
    base = rng.normal(1.0, 0.1, 10_000)
    signal = rng.normal(1.8, 0.1, 100)
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="volatility")
    assert res["p_greater"] < 0.01


def test_volatility_ratio_permutation_detects_real_contraction():
    """NEGATİF KONTROL (Volatilite Modu): Gerçek volatilite daralması tespit edilmeli."""
    rng = np.random.default_rng(5)
    base = rng.normal(1.0, 0.1, 10_000)
    signal = rng.normal(0.4, 0.1, 100)
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="volatility")
    assert res["p_less"] < 0.01


def test_volatility_ratio_permutation_finds_nothing_on_noise():
    """SIFIR KONTROLÜ (Volatilite Modu): Genişleme yoksa p uçlarda olmamalı."""
    rng = np.random.default_rng(6)
    base = rng.normal(1.0, 0.1, 10_000)
    signal = rng.normal(1.0, 0.1, 100)
    res = permutation_test(signal, base, 0.5, 2000, rng, mode="volatility")
    assert 0.02 < res["p_greater"] < 0.98


def test_benjamini_hochberg_correction_adjusts_p_values():
    """BH FDR algoritması birim testi."""
    raw_p = [0.001, 0.01, 0.04, 0.20, 0.50]
    adj_p = benjamini_hochberg(raw_p)
    assert len(adj_p) == len(raw_p)
    assert adj_p[0] <= adj_p[1] <= adj_p[2] <= adj_p[3] <= adj_p[4]
    for r, a in zip(raw_p, adj_p, strict=True):
        assert a >= r


def test_fomc_calendar_loading():
    """FOMC takvim dosyasının doğru yüklendiği ve tarih formatı testi."""
    df = load_fomc_calendar()
    assert not df.empty
    assert "datetime" in df.columns
    assert df["datetime"].dt.tz is not None
