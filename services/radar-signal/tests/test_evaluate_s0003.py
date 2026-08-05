"""S-0003 Hipotez Değerlendirme Motoru Testleri (ADR-0017)."""

import pandas as pd

from scripts.evaluate_s0003 import compute_funding_signals, run_s0003_evaluation


def test_compute_funding_signals_logic():
    """Settled funding persentil ve sinyal mantığını doğrular."""
    dates = pd.date_range("2024-01-01", periods=1000, freq="1h", tz="UTC")

    # Generate synthetic candle dataframe
    c_df = pd.DataFrame(
        {
            "date_dt": dates,
            "open": 50000.0,
            "high": 50500.0,
            "low": 49500.0,
            "close": 50100.0,
        }
    )

    # Generate synthetic funding dataframe with periodic highs and lows
    fr_vals = [0.0001] * 1000
    for i in range(100, 200):
        fr_vals[i] = 0.0010  # High positive funding -> SHORT signal
    for i in range(300, 400):
        fr_vals[i] = -0.0010  # High negative funding -> LONG signal

    fr_df = pd.DataFrame({"date_dt": dates, "open": fr_vals})

    merged = compute_funding_signals(fr_df, c_df, rolling_days=10)
    assert "funding_pct" in merged.columns
    assert "signal" in merged.columns
    assert "fwd_24h_raw" in merged.columns

    # High funding produces SHORT (-1)
    short_signals = (merged["signal"] == -1).sum()
    assert short_signals > 0

    # Low funding produces LONG (+1)
    long_signals = (merged["signal"] == 1).sum()
    assert long_signals > 0


def test_run_s0003_evaluation_execution():
    """Gerçek veride S-0003 değerlendirmesinin sızıntısız çalıştığını doğrular."""
    res = run_s0003_evaluation()
    assert res["hypothesis_id"] == "S-0003"
    assert res["total_trades"] > 0
    assert "verdict" in res
    assert "registry_experiment_id" in res
    assert "provenance" in res
    assert "rejected" in res["verdict"]
