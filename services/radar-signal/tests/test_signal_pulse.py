"""Nabız analizi testleri — ölçüm aracının kendisi doğru mu?

Bu script bir hipotezi kapatma yetkisi taşıyor (ADR-0006), dolayısıyla aracın
sentetik veri üzerinde bilinen cevabı bulduğu kanıtlanmalı. Aksi halde "öngörü gücü
yok" hükmü, aracın körlüğünden de kaynaklanıyor olabilirdi.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from signal_pulse import HORIZONS, build_signals, permutation_test  # noqa: E402


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
    d = build_signals(_frame(), window=80)
    row = 500
    for h in HORIZONS:
        expected = d["close"].iloc[row + h] / d["close"].iloc[row] - 1.0
        assert d[f"fwd_{h}"].iloc[row] == pytest.approx(expected)


def test_last_bars_have_no_forward_return():
    """Serinin sonunda ileri getiri tanımsız olmalı — uydurulmamalı."""
    d = build_signals(_frame(), window=80)
    assert d["fwd_16"].iloc[-1] != d["fwd_16"].iloc[-1]  # NaN


def test_signals_are_produced_and_directional():
    d = build_signals(_frame(), window=80)
    assert (d["direction"] != 0).sum() > 0
    assert set(d["direction"].unique()) <= {-1, 0, 1}


def test_breakout_condition_uses_only_past_bars():
    """Kırılım eşiği shift(1)'li olmalı: bar kendi high'ını aşamaz."""
    d = build_signals(_frame(), window=80)
    row = d[d["direction"] == 1].index[0]
    assert d["close"].iloc[row] > d["hmax"].iloc[row]
    prior_high = d["high"].iloc[row - 4 : row].max()
    assert d["hmax"].iloc[row] == pytest.approx(prior_high)


def test_permutation_detects_real_positive_edge():
    """POZİTİF KONTROL: gerçek avantaj varsa test onu bulmalı."""
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(0.004, 0.01, 800)  # +40 bps gerçek avantaj
    res = permutation_test(signal, base, 0.5, 2000, rng)
    assert res["p_greater"] < 0.01
    assert res["p_less"] > 0.99


def test_permutation_detects_real_negative_edge():
    """NEGATİF KONTROL: Kart A'da bulunan yön — anlamlı KÖTÜ tespit edilmeli."""
    rng = np.random.default_rng(2)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(-0.004, 0.01, 800)
    res = permutation_test(signal, base, 0.5, 2000, rng)
    assert res["p_less"] < 0.01


def test_permutation_finds_nothing_when_there_is_nothing():
    """SIFIR KONTROLÜ: avantaj yoksa p değerleri uçlarda olmamalı."""
    rng = np.random.default_rng(3)
    base = rng.normal(0, 0.01, 50_000)
    signal = rng.normal(0, 0.01, 800)
    res = permutation_test(signal, base, 0.5, 2000, rng)
    assert 0.02 < res["p_greater"] < 0.98
    assert 0.02 < res["p_less"] < 0.98


def test_null_distribution_is_centred_on_zero():
    """Taban yön ataması tarafsız olmalı — ilk sürümde dönem trendi sızıyordu."""
    rng = np.random.default_rng(4)
    base = rng.normal(0.002, 0.01, 50_000)  # trendli dönem
    res = permutation_test(np.zeros(500), base, 0.5, 2000, rng)
    assert abs(res["null_mean_bps"]) < 5.0  # trend taşınmamalı


def test_window_choice_changes_signal_set():
    a = build_signals(_frame(), window=80)
    b = build_signals(_frame(), window=240)
    assert not a["direction"].equals(b["direction"])
