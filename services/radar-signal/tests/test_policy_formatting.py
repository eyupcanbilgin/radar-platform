"""Fail-closed politikası (P0-8) + bildirim dili (kural 10) testleri."""

import pytest

from enricher.formatting import (
    ForbiddenLanguage,
    assert_language_safe,
    build_exit_message,
    build_no_trade_card,
    build_signal_message,
)
from enricher.policy import evaluate_inputs, load_lifecycle

ALL_OK = {
    "candle_close": True,
    "price": True,
    "atr": True,
    "regime": True,
    "blackout_calendar": True,
}


@pytest.fixture
def lifecycle():
    return load_lifecycle()


def test_all_inputs_present_approves(lifecycle):
    res = evaluate_inputs(ALL_OK, lifecycle)
    assert res.approved and not res.degraded_flags and res.block_reason is None


def test_missing_required_blocks(lifecycle):
    res = evaluate_inputs({**ALL_OK, "atr": False}, lifecycle)
    assert res.approved is False
    assert "ZORUNLU GİRDİ EKSİK" in res.block_reason and "atr" in res.block_reason


def test_absent_key_counts_as_missing(lifecycle):
    """Listede hiç görünmeyen zorunlu girdi 'var' sayılmaz (sessiz varsayım yok)."""
    res = evaluate_inputs({"price": True, "atr": True}, lifecycle)
    assert res.approved is False and "candle_close" in res.block_reason


def test_missing_optional_regime_degrades_not_blocks(lifecycle):
    res = evaluate_inputs({**ALL_OK, "regime": False}, lifecycle)
    assert res.approved is True
    assert res.degraded_inputs == ["regime"]
    assert res.degraded_flags == ["REJİM ÇEVRİMDIŞI — değerlendirilemedi"]


def test_optional_without_flag_fails_loud(lifecycle):
    broken = {
        **lifecycle,
        "inputs": {"required": ["price"], "optional": ["etiketsiz_katman"]},
    }
    with pytest.raises(ValueError, match="etiketi olmayan"):
        evaluate_inputs({"price": True, "etiketsiz_katman": False}, broken)


def test_empty_required_config_fails_loud(tmp_path):
    p = tmp_path / "lifecycle.yaml"
    p.write_text(
        "version: '1'\ninputs:\n  required: []\ndegraded_flags: {}\nvalidity: {}\n"
        "exit_precedence: []\noutbox: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fail-closed"):
        load_lifecycle(p)


# --- Dil kuralları (kural 10 / CR-002 P2-8) --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "BTC al",
        "Şimdi sat",
        "Fiyat kesin yükselir",
        "Bu seviyeden alım yapın",
        "STOP ÇALIŞTI — pozisyon kapandı",
        "Garanti kâr",
        "mutlaka izleyin",
    ],
)
def test_forbidden_language_is_caught(text):
    with pytest.raises(ForbiddenLanguage):
        assert_language_safe(text)


@pytest.mark.parametrize(
    "text",
    [
        "İnvalidasyon seviyesi 61.250,00",
        "Sinyal satırı gerekçeyle birlikte iletildi",
        "SİSTEM İNVALIDASYONU — referans fiyat stop seviyesini geçti",
        "Referans giriş bölgesi hesaplandı",
    ],
)
def test_safe_language_passes(text):
    assert_language_safe(text)


def _msg(**over):
    base = dict(
        signal_id="BTC-S0002-20260803-1200-L-01",
        asset="BTC",
        direction="LONG",
        timeframe="15m",
        candle_close_utc="2026-08-03 12:00",
        strategy="S0002",
        enter_tag="volume_confirmed_momentum",
        rationale="1h EMA50 üstünde; 15m hacim 20-bar ortalamasının üstünde",
        counter_evidence="Funding 90 günlük yüzdelik %92 — kaldıraç birikimi yüksek",
        entry_reference=61250.0,
        invalidation=60100.0,
        valid_until_utc="2026-08-03 12:15",
        max_entry_deviation_pct=0.35,
        regime_line="yön +31, kırılganlık 44, güven 78",
        data_health="87/100 · Stale: Korea Premium 22dk",
    )
    base.update(over)
    return build_signal_message(**base)


def test_signal_message_has_mandatory_blocks():
    text = _msg()
    assert "İnvalidasyon" in text
    assert "yatırım tavsiyesi değildir" in text
    assert "Geçerlilik:" in text and "sapma sonrası kurulum bozulur" in text
    assert "Destekleyen:" in text and "Karşı çıkan:" in text  # P2-4
    assert "Veri sağlığı:" in text  # P2-5
    assert "BTC-S0002-20260803-1200-L-01" in text  # P2-6


def test_degraded_flag_surfaces_in_message():
    text = _msg(degraded_flags=["REJİM ÇEVRİMDIŞI — değerlendirilemedi"])
    assert "UYARI: REJİM ÇEVRİMDIŞI" in text


def test_missing_levels_do_not_fake_numbers():
    text = _msg(entry_reference=None, invalidation=None)
    assert "hesaplanamadı" in text


def test_exit_message_uses_invalidation_language():
    text = build_exit_message(
        signal_id="BTC-S0002-20260803-1200-L-01",
        asset="BTC",
        exit_state="STOP_EXIT",
        reason="atr_stop_touched",
        reference_price=60100.0,
    )
    assert "SİSTEM İNVALIDASYONU" in text
    assert "otomatik kapatılmadı" in text
    assert "STOP ÇALIŞTI" not in text


def test_no_trade_card_is_first_class_output():
    text = build_no_trade_card(
        as_of_utc="2026-08-03 12:00",
        regime_line="yön +5, kırılganlık 62, güven 71",
        blockers=["karartma aktif (FOMC)", "kırılganlık ≥60"],
        data_health="91/100",
    )
    assert "yeni yönsel sinyal üretilmedi" in text
    assert "karartma aktif" in text
