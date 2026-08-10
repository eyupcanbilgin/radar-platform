"""Fully synthetic tests for cross-venue execution of a pre-registered signal.

No network, no `user_data/`, no live registry: every frame is built in memory.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from scripts.venue_robustness import collect_venue_returns

FEE = {"realistic": 0.0002, "taker_heavy": 0.0006}


def _signals(hours: int = 200) -> pd.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(hours):
        rows.append(
            {
                "date_dt": start + timedelta(hours=index),
                # Her 48 saatte bir LONG; ufuk 24 saat olduğu için örtüşme yok.
                "signal": 1 if index % 48 == 0 else 0,
            }
        )
    return pd.DataFrame(rows)


def _prices(hours: int = 200, *, drift: float = 0.001) -> pd.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    price = 40_000.0
    for index in range(hours):
        price *= 1.0 + drift
        rows.append(
            {
                "date_dt": start + timedelta(hours=index),
                "perp_open": price,
                "perp_close": price * 1.0005,
            }
        )
    return pd.DataFrame(rows)


def _plan(hours: int = 200) -> dict:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return {
        "folds": [
            {
                "fold_index": 0,
                "status": "valid",
                "test_start_utc": start.isoformat().replace("+00:00", "Z"),
                "test_end_utc": (start + timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
            }
        ]
    }


def test_same_signal_is_executed_on_every_venue():
    result = collect_venue_returns(
        signals_frame=_signals(),
        venue_frames={
            "binance": _prices(drift=0.001),
            "bybit": _prices(drift=0.001),
        },
        plan=_plan(),
        fee=FEE,
    )
    assert sorted(result) == ["binance", "bybit"]
    # Aynı fiyat serisi → aynı sonuç; mekân farkı gürültüden gelmiyor.
    assert result["binance"]["realistic"] == result["bybit"]["realistic"]
    assert result["binance"]["realistic"]


def test_a_venue_with_worse_prices_produces_worse_returns():
    """Kapının ölçtüğü asıl soru: aynı kural başka yerde de para kazandırır mıydı?"""
    result = collect_venue_returns(
        signals_frame=_signals(),
        venue_frames={
            "rising": _prices(drift=0.002),
            "falling": _prices(drift=-0.002),
        },
        plan=_plan(),
        fee=FEE,
    )
    assert sum(result["rising"]["realistic"]) > sum(result["falling"]["realistic"])


def test_missing_hours_are_dropped_not_imputed():
    """Mekânda olmayan saat için işlem uydurulmaz; o sinyal orada gerçekleşmemiştir."""
    signals = _signals()
    prices = _prices()
    # Bu mekânın geçmişi 100. saatte bitiyor: 0 ve 48'deki sinyaller işlenebilir,
    # 96 ve 144'tekiler işlenemez (96 için +24h çıkış barı da yok).
    truncated = prices[prices["date_dt"] < prices["date_dt"].iloc[100]].reset_index(drop=True)

    partial = collect_venue_returns(
        signals_frame=signals, venue_frames={"short": truncated}, plan=_plan(), fee=FEE
    )
    full = collect_venue_returns(
        signals_frame=signals, venue_frames={"full": prices}, plan=_plan(), fee=FEE
    )
    assert len(partial["short"]["realistic"]) < len(full["full"]["realistic"])
    assert len(partial["short"]["realistic"]) > 0


def test_no_overlap_between_signal_and_venue_is_fail_loud():
    """Sessizce boş dönmek 'bu mekânda sonuç yoktu' gibi okunurdu."""
    far_future = _prices()
    far_future["date_dt"] = far_future["date_dt"] + timedelta(days=3650)
    with pytest.raises(ValueError, match="kesişmiyor"):
        collect_venue_returns(
            signals_frame=_signals(),
            venue_frames={"elsewhere": far_future},
            plan=_plan(),
            fee=FEE,
        )


def test_empty_venue_set_is_rejected():
    with pytest.raises(ValueError, match="en az bir mekân"):
        collect_venue_returns(signals_frame=_signals(), venue_frames={}, plan=_plan(), fee=FEE)


def test_signal_frame_must_carry_the_preregistered_signal_column():
    frame = _signals().drop(columns=["signal"])
    with pytest.raises(ValueError, match="eksik kolon"):
        collect_venue_returns(
            signals_frame=frame,
            venue_frames={"binance": _prices()},
            plan=_plan(),
            fee=FEE,
        )
