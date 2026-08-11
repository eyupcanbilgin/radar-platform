"""On-chain günlük seri indiricisi (tamamen sentetik; ağa çıkılmaz).

Bu dosyanın koruduğu asıl şey look-ahead'dir: günlük bir metrik gün kapanmadan var olamaz.
Satır kendi gününde kullanılabilir sayılırsa ölçüm gelecekten bilgi taşır ve hipotez
ölçülmemiş olur.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from download_onchain_daily import (  # noqa: E402
    PUBLICATION_LAG_HOURS,
    available_at,
    to_frame,
)

VALUE = "sthSopr"
FAR_FUTURE = datetime(2030, 1, 1, tzinfo=UTC)


def _rows(*days: str) -> list[dict]:
    return [{"d": day, "unixTs": 0, VALUE: 1.0 + index} for index, day in enumerate(days)]


def _frame(rows, *, until=FAR_FUTURE):
    return to_frame(rows, value_key=VALUE, until_utc=until)


def test_a_days_value_is_never_available_inside_that_day():
    """En temel kural: D gününü özetleyen satır D kapanmadan bilinemez."""
    day_start = datetime(2026, 8, 10, tzinfo=UTC)
    day_end = datetime(2026, 8, 11, tzinfo=UTC)

    assert available_at(day_start) >= day_end


def test_availability_is_the_day_close_plus_the_frozen_lag():
    frame = _frame(_rows("2026-08-10"))

    assert frame["event_time_utc"].iloc[0] == datetime(2026, 8, 11, tzinfo=UTC)
    assert frame["available_at_utc"].iloc[0] == datetime(2026, 8, 12, tzinfo=UTC)
    assert PUBLICATION_LAG_HOURS == 24


def test_the_boundary_cuts_on_availability_not_on_the_day():
    """Sınırdan önceki güne ait ama sınırdan SONRA doğan satır dosyaya giremez.

    Gün üzerinden kesilseydi `2026-08-03` satırı (04:00'te doğar) Locked OOS eğitim
    dosyasına girer ve sınırı içeriden delerdi.
    """
    rows = _rows("2026-08-01", "2026-08-02", "2026-08-03")

    frame = _frame(rows, until=datetime(2026, 8, 4, tzinfo=UTC))

    assert list(frame["day"]) == ["2026-08-01"]


def test_missing_calendar_days_are_reported_not_filled():
    frame = _frame(_rows("2026-08-01", "2026-08-04"))

    gaps = frame.attrs["coverage"]["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["missing_days"] == 2
    assert len(frame) == 2  # boşluk uydurulmuş satırla kapatılmadı


def test_rows_are_ordered_by_time_regardless_of_response_order():
    frame = _frame(_rows("2026-08-03", "2026-08-01", "2026-08-02"))

    assert list(frame["day"]) == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_a_duplicated_day_fails_loudly():
    with pytest.raises(ValueError, match="aynı gün"):
        _frame(_rows("2026-08-01") + _rows("2026-08-01"))


@pytest.mark.parametrize("bad", [None, "yok", True, {}])
def test_an_unparseable_value_fails_loudly_instead_of_becoming_zero(bad):
    """Eksik veri sıfır değildir; sessiz 0 ölçümü bozardı."""
    with pytest.raises(ValueError):
        _frame([{"d": "2026-08-01", VALUE: bad}])


def test_a_missing_value_field_fails_loudly():
    with pytest.raises(ValueError, match="sthSopr"):
        _frame([{"d": "2026-08-01", "unixTs": 0}])


def test_a_malformed_day_fails_loudly():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _frame([{"d": "11/08/2026", VALUE: 1.0}])


def test_an_empty_series_never_becomes_an_empty_file():
    with pytest.raises(ValueError, match="boş döndü"):
        _frame([])


def test_a_boundary_that_excludes_everything_fails_instead_of_writing_nothing():
    with pytest.raises(ValueError, match="kullanılabilir satır yok"):
        _frame(_rows("2026-08-01"), until=datetime(2026, 8, 1, tzinfo=UTC))


def test_a_naive_boundary_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        _frame(_rows("2026-08-01"), until=datetime(2026, 8, 4))
