"""Drift raporu testleri: mum-içi çıkış tespiti doğru sınıflandırıyor mu?"""

import pandas as pd
from drift_report import analyse


def _trades(close_dates, profits, reasons=None):
    return pd.DataFrame(
        {
            "close_date": pd.to_datetime(close_dates, utc=True),
            "profit_abs": profits,
            "exit_reason": reasons or ["exit_signal"] * len(profits),
        }
    )


def test_empty_input():
    assert analyse(pd.DataFrame())["trades"] == 0


def test_candle_close_exits_are_not_drift():
    df = _trades(["2026-08-03 12:00:00", "2026-08-03 12:15:00", "2026-08-03 12:30:00"], [1, 2, 3])
    stats = analyse(df)
    assert stats["intracandle_exits"] == 0
    assert stats["pnl_on_candle_close"] == 6.0


def test_intracandle_exits_detected():
    df = _trades(["2026-08-03 12:07:00", "2026-08-03 12:15:00"], [-5.0, 2.0])
    stats = analyse(df)
    assert stats["intracandle_exits"] == 1
    assert stats["intracandle_share_pct"] == 50.0
    assert stats["pnl_intracandle"] == -5.0
    assert stats["pnl_on_candle_close"] == 2.0


def test_nonzero_seconds_count_as_intracandle():
    """12:15:30 mum kapanışı DEĞİLDİR; dakika hizası tek başına yetmez."""
    df = _trades(["2026-08-03 12:15:30"], [1.0])
    assert analyse(df)["intracandle_exits"] == 1


def test_exit_reason_breakdown():
    df = _trades(
        ["2026-08-03 12:07:00", "2026-08-03 12:09:00", "2026-08-03 12:30:00"],
        [-1.0, -2.0, 3.0],
        ["trailing_stop_loss", "stop_loss", "exit_signal"],
    )
    stats = analyse(df)
    assert stats["exit_reasons_intracandle"] == {"trailing_stop_loss": 1, "stop_loss": 1}
