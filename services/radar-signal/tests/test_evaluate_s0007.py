"""S-0007 sinyal mekaniği testleri (tamamen sentetik; diske ve ağa bağımlı değil).

Bu dosyanın koruduğu şey karttaki dondurulmuş kurallardır (`docs/hypotheses/S-0007.md`,
commit 37553b5): yayın anı, yönün işareti, mutlak eşiğin yokluğu ve günlük bir değerin
saatlere yayılmaması.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from scripts.evaluate_s0007 import BASE_PARAMETERS, VALUE_COLUMN, compute_s0007_signals

START = datetime(2026, 1, 1, tzinfo=UTC)


def _daily(values: list[float], *, start: datetime = START) -> pd.DataFrame:
    """Günlük on-chain seri; `available_at` gün kapanışı + 24 saat (ADR-0050)."""
    rows = []
    for index, value in enumerate(values):
        day_start = start + timedelta(days=index)
        rows.append(
            {
                "day": day_start.date().isoformat(),
                "event_time_utc": day_start + timedelta(days=1),
                "available_at_utc": day_start + timedelta(days=2),
                VALUE_COLUMN: value,
            }
        )
    return pd.DataFrame(rows)


def _perp(hours: int, *, start: datetime = START) -> pd.DataFrame:
    stamps = pd.date_range(start, periods=hours, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "date_dt": stamps,
            "perp_open": np.linspace(100.0, 200.0, hours),
            "perp_close": np.linspace(100.5, 200.5, hours),
        }
    )


def _signals(values: list[float], **overrides):
    parameters = {**BASE_PARAMETERS, **overrides}
    return compute_s0007_signals(
        _daily(values),
        _perp(hours=(len(values) + 4) * 24),
        sopr_smooth_days=int(parameters["sopr_smooth_days"]),
        sopr_dist_days=int(parameters["sopr_dist_days"]),
        upper_percentile=float(parameters["upper_percentile"]),
        lower_percentile=float(parameters["lower_percentile"]),
    )


def _flat_then(final: float, *, days: int = 40) -> list[float]:
    """Sabit taban üstüne son üç günde `final`.

    Taban bilinçli olarak SABİTTİR: monoton bir rampa, serinin kendi hareketli penceresinde
    hem alt hem üst ucu üretir ve testin ölçmek istediği işareti bulanıklaştırırdı. Sabit
    tabanda bağların midrank'i ortadadır, dolayısıyla yalnız kuyruk uca gider.
    """
    return [1.0] * (days - 3) + [final, final, final]


def test_a_days_value_is_never_used_before_its_publication_hour():
    """En temel kural: değer `available_at`ten önceki hiçbir saatte sinyal üretemez."""
    frame = _signals(_flat_then(0.5))

    fired = frame[frame["signal"] != 0]
    assert not fired.empty
    for _, row in fired.iterrows():
        assert row["date_dt"] == row["available_at_utc"]


def test_sustained_realized_loss_is_long_not_short():
    """Kartta dondurulmuş işaret: düşük yüzdelik (zarar) LONG'dur.

    Bu testin varlık sebebi: sonucu görüp yönü ters çevirmek yasak. İşaret burada
    mekanizmadan bağımsız olarak sabitlenmiştir.
    """
    frame = _signals(_flat_then(0.5))
    fired = frame[frame["signal"] != 0]

    assert set(fired["signal"].unique()) == {1}
    assert (fired["sopr_pct_rank"] <= BASE_PARAMETERS["lower_percentile"]).all()


def test_sustained_realized_profit_is_short():
    frame = _signals(_flat_then(1.6))
    fired = frame[frame["signal"] != 0]

    assert set(fired["signal"].unique()) == {-1}
    assert (fired["sopr_pct_rank"] >= BASE_PARAMETERS["upper_percentile"]).all()


def test_a_daily_value_produces_at_most_one_decision_hour_per_day():
    """Günlük değeri 24 saate yaymak örneklemi sahte biçimde 24 katına çıkarırdı."""
    frame = _signals(_flat_then(0.5))
    fired = frame[frame["signal"] != 0]

    per_day = fired["date_dt"].dt.date.value_counts()
    assert (per_day == 1).all()
    assert (fired["date_dt"].dt.hour == 0).all()


def test_the_break_even_level_is_not_a_threshold():
    """`SOPR = 1.0` doğal dönüm noktasıdır ve kart §4.3 gereği KULLANILMAZ.

    Tamamı 1.0'ın altında olan bir seri, mutlak eşik kullanılsaydı baştan sona LONG
    üretirdi. Göreli yüzdelikle sinyal yalnız serinin **kendi** dağılımının ucunda doğar.
    """
    below = list(np.linspace(0.80, 0.95, 40))

    frame = _signals(below)
    fired = frame[frame["signal"] != 0]

    assert len(fired) < 40  # hepsi tetiklemedi
    assert (fired["signal"] == -1).any()  # kendi dağılımının üstü SHORT üretebiliyor


def test_an_unknown_percentile_is_wait_not_neutral_zero():
    """Yüzdelik hesaplanamıyorsa (yetersiz geçmiş) sinyal üretilmez; bilinmeyen nötr değildir."""
    frame = _signals([1.0] * 5)  # dağılım penceresi için çok kısa

    assert (frame["signal"] == 0).all()
    assert frame["sopr_pct_rank"].isna().all()


def test_hours_without_a_published_value_stay_wait():
    frame = _signals(_flat_then(0.5))
    idle = frame[frame["available_at_utc"].isna()]

    assert not idle.empty
    assert (idle["signal"] == 0).all()


def test_forward_return_enters_on_the_next_open_and_exits_24h_later():
    """Look-ahead yasağı: giriş karar saatinin SONRAKİ açılışıdır."""
    frame = _signals(_flat_then(0.5))
    row = 10
    entry = frame["perp_open"].iloc[row + 1]
    exit_price = frame["perp_close"].iloc[row + 24]

    assert np.isclose(frame["fwd_24h_raw"].iloc[row], (exit_price - entry) / entry)
