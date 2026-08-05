"""S-0003 Hipotez Değerlendirme Motoru Testleri (ADR-0017).

Bu testler tam sentetik veri üzerinde çalışır ve CI ortamında gitignore'lu
disk verisi olmadan mekaniği (persentil, maliyet düşüşü, ret kriterleri) doğrular.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.evaluate_s0003 import compute_funding_signals, run_s0003_evaluation


def _make_synthetic_dfs():
    """CI ve birim testleri için tam sentetik mum ve funding verisi üretir."""
    dates = pd.date_range("2023-12-01T00:00:00Z", "2026-08-04T00:00:00Z", freq="1h")
    n = len(dates)

    # Deterministic price series with subtle fluctuations
    np.random.seed(42)
    p_changes = np.random.normal(0, 10, n)
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

    # Periodic extreme funding values to trigger signals
    fr_vals = np.full(n, 0.0001)
    for i in range(1000, 1200):
        fr_vals[i] = 0.0015  # High funding -> SHORT
    for i in range(3000, 3200):
        fr_vals[i] = -0.0015  # Low funding -> LONG

    fr_df = pd.DataFrame({"date_dt": dates, "open": fr_vals})
    return fr_df, c_df


def test_compute_funding_signals_logic():
    """Settled funding persentil ve sinyal mantığını doğrular."""
    fr_df, c_df = _make_synthetic_dfs()
    merged = compute_funding_signals(fr_df, c_df, rolling_days=30)

    assert "funding_pct" in merged.columns
    assert "signal" in merged.columns
    assert "fwd_24h_raw" in merged.columns

    # High funding produces SHORT (-1)
    short_signals = (merged["signal"] == -1).sum()
    assert short_signals > 0

    # Low funding produces LONG (+1)
    long_signals = (merged["signal"] == 1).sum()
    assert long_signals > 0


def test_run_s0003_evaluation_synthetic_mechanics(tmp_path, monkeypatch):
    """CI uyumlu sentetik veri ile S-0003 değerlendirme mekaniğini doğrular."""
    fr_df, c_df = _make_synthetic_dfs()

    mock_manifest = {"status": "ok", "checked": 10, "manifest": "MANIFEST-20260804.json"}

    with (
        patch("scripts.evaluate_s0003.verify_manifest", return_value=mock_manifest),
        patch("scripts.evaluate_s0003.load_data", return_value=(fr_df, c_df)),
    ):
        reg_file = tmp_path / "experiments.jsonl"
        res = run_s0003_evaluation(registry_path=reg_file)

        assert res["hypothesis_id"] == "S-0003"
        assert res["strategy"] == "S0003FundingExtreme"
        assert "performance" in res
        assert "realistic" in res["performance"]
        assert "taker_heavy" in res["performance"]
        assert "verdict" in res
        assert "rejection_reasons" in res
        assert "registry_experiment_id" in res
        assert reg_file.exists()
