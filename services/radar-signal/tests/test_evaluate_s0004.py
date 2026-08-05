"""S-0004 Hipotez Değerlendirme Motoru Testleri (ADR-0018).

Bu testler tam sentetik veri üzerinde çalışır ve CI ortamında gitignore'lu
disk verisi olmadan mekaniği (persentil, volatilite kapısı, WAIT üretimi,
maliyet düşüşü ve ret kriterleri) doğrular.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.evaluate_s0004 import compute_s0004_signals, run_s0004_evaluation


def _make_synthetic_candle_df():
    """CI ve birim testleri için tam sentetik 1h mum verisi üretir."""
    dates = pd.date_range("2023-12-01T00:00:00Z", "2026-08-04T00:00:00Z", freq="1h")
    n = len(dates)

    np.random.seed(42)
    p_changes = np.random.normal(0, 15, n)
    # Volatility bursts around middle section
    p_changes[2000:2500] *= 5.0
    p_changes[5000:5500] *= 0.05

    prices = np.cumsum(p_changes) + 50000.0
    prices = np.maximum(prices, 1000.0)

    c_df = pd.DataFrame(
        {
            "date_dt": dates,
            "open": prices,
            "high": prices + 50.0,
            "low": prices - 50.0,
            "close": prices + 5.0,
            "volume": 100.0,
        }
    )
    return c_df


def test_compute_s0004_signals_mechanics():
    """Volatilite kapısı ve WAIT rejimlerinin mekanik doğrulamasını yapar."""
    c_df = _make_synthetic_candle_df()
    df_signals = compute_s0004_signals(
        c_df,
        trend_days=10,
        vol_calc_days=5,
        vol_dist_days=20,
        vol_lower_pct=0.20,
        vol_upper_pct=0.80,
    )

    assert "price_pct" in df_signals.columns
    assert "realized_vol" in df_signals.columns
    assert "vol_pct" in df_signals.columns
    assert "signal" in df_signals.columns

    # Verify signals contain LONG (1), SHORT (-1), and WAIT (0)
    signals = df_signals["signal"].unique()
    assert 0 in signals  # WAIT regime must exist
    assert 1 in signals or -1 in signals

    # Verify that when vol_pct < 0.20 or > 0.80, signal is ALWAYS 0 (WAIT)
    out_of_band_mask = (df_signals["vol_pct"] < 0.20) | (df_signals["vol_pct"] > 0.80)
    assert (df_signals.loc[out_of_band_mask, "signal"] == 0).all()


def test_run_s0004_evaluation_synthetic_mechanics(tmp_path):
    """CI uyumlu sentetik veri ile S-0004 değerlendirme mekaniğini doğrular."""
    c_df = _make_synthetic_candle_df()
    mock_manifest = {"status": "ok", "checked": 10, "manifest": "MANIFEST-20260804.json"}

    with (
        patch("scripts.evaluate_s0004.verify_manifest", return_value=mock_manifest),
        patch("scripts.evaluate_s0004.load_candle_data", return_value=c_df),
    ):
        reg_file = tmp_path / "experiments.jsonl"
        res = run_s0004_evaluation(registry_path=reg_file)

        assert res["hypothesis_id"] == "S-0004"
        assert res["strategy"] == "S0004VolConditionedTrend"
        assert "performance" in res
        assert "realistic" in res["performance"]
        assert "taker_heavy" in res["performance"]
        assert "verdict" in res
        assert "rejection_reasons" in res
        assert "registry_experiment_id" in res
        assert reg_file.exists()
