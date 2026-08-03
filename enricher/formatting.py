"""Bildirim metinleri — CLAUDE.md kural 10 (yatırım tavsiyesi dili yasak).

İki koruma katmanı:
1. Şablonlar zaten koşullu/referans dilinde yazılmıştır (emir kipi yok).
2. `assert_language_safe()` her giden metni tarar; yasak kalıp bulursa gönderimi
   DURDURUR. Bu, gelecekte şablona sızacak bir "al/sat" ifadesini üretimde değil
   testte yakalamak içindir.

Dil kararı (CR-002 P2-8): "STOP ÇALIŞTI — pozisyon kapandı" YASAK; doğrusu
"SİSTEM İNVALIDASYONU — referans fiyat stop seviyesini geçti; gerçek pozisyonunuz
otomatik kapatılmadı." Sistem defteri kullanıcının gerçek pozisyonu değildir.
"""

import re

LEGAL_NOTE = "Araştırma sinyalidir; yatırım tavsiyesi değildir. Karar ve risk kullanıcıya aittir."

# Kelime sınırlı yasak kalıplar. Gerekçe: "sinyal", "invalidasyon", "satır" gibi
# masum kelimeler içindeki harf dizileri yakalanmamalı.
FORBIDDEN = [
    r"\bal\b",
    r"\bsat\b",
    r"\balın\b",
    r"\bsatın\b",
    r"\balım\b",
    r"\bsatış\b",
    r"\bkesin\b",
    r"\bkesinlikle\b",
    r"\bgaranti\b",
    r"\bmutlaka\b",
    r"\btavsiye ediyorum\b",
    r"\bönerilir\b",
    r"stop çalıştı",
    r"pozisyon kapandı",
]
_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]


class ForbiddenLanguage(Exception):
    """Yatırım tavsiyesi diline benzeyen ifade tespit edildi (kural 10)."""


def assert_language_safe(text: str) -> None:
    hits = sorted({m.group(0).lower() for p in _PATTERNS for m in p.finditer(text)})
    if hits:
        raise ForbiddenLanguage(
            f"yasak dil kalıbı: {hits} — kural 10; metin koşullu/referans diline çevrilmeli"
        )


def _levels_block(entry_reference: float | None, invalidation: float | None) -> str:
    if entry_reference is None or invalidation is None:
        return "Referans seviyeler: hesaplanamadı"
    return (
        f"Referans giriş bölgesi: {entry_reference:,.2f} · "
        f"İnvalidasyon (fikrin geçersizleştiği seviye): {invalidation:,.2f}"
    )


def build_signal_message(
    *,
    signal_id: str,
    asset: str,
    direction: str,
    timeframe: str,
    candle_close_utc: str,
    strategy: str,
    enter_tag: str,
    rationale: str,
    entry_reference: float | None,
    invalidation: float | None,
    valid_until_utc: str,
    max_entry_deviation_pct: float,
    regime_line: str,
    data_health: str,
    counter_evidence: str,
    degraded_flags: list[str] | None = None,
) -> str:
    lines = [
        f"[SİNYAL] {asset} {direction} · {timeframe} · {candle_close_utc} UTC",
        f"Kimlik: {signal_id}",
        f"Strateji: {strategy} · etiket: {enter_tag}",
        f"Destekleyen: {rationale}",
        f"Karşı çıkan: {counter_evidence}",
        f"Rejim: {regime_line}",
        _levels_block(entry_reference, invalidation),
        f"Geçerlilik: {valid_until_utc} UTC'ye kadar · "
        f"referanstan %{max_entry_deviation_pct:.2f} sapma sonrası kurulum bozulur",
        f"Veri sağlığı: {data_health}",
    ]
    for flag in degraded_flags or []:
        lines.append(f"UYARI: {flag}")
    lines.append(f"Not: {LEGAL_NOTE}")
    text = "\n".join(lines)
    assert_language_safe(text)
    return text


def build_exit_message(
    *, signal_id: str, asset: str, exit_state: str, reason: str, reference_price: float | None
) -> str:
    headline = {
        "STOP_EXIT": "SİSTEM İNVALIDASYONU — referans fiyat stop seviyesini geçti",
        "INVALIDATED": "SİSTEM İNVALIDASYONU — kurulum geçersizleşti",
        "ROI_EXIT": "REFERANS HEDEF BÖLGESİ GÖRÜLDÜ",
        "STRATEGY_EXIT": "KURAL ÇIKIŞI — strateji koşulu sona erdi",
        "TIME_EXIT": "SÜRE ÇIKIŞI — tanımlı izleme penceresi doldu",
        "DATA_FAILURE_EXIT": "VERİ ARIZASI — izleme sürdürülemedi",
    }.get(exit_state, f"REFERANS DEFTERİ KAPANDI ({exit_state})")

    price_line = (
        f"Referans fiyat: {reference_price:,.2f}"
        if reference_price is not None
        else "Referans fiyat: yok"
    )
    text = "\n".join(
        [
            f"[KAPANIŞ] {asset} · {signal_id}",
            headline,
            "Sistem defteri hipotetiktir; gerçek pozisyonunuz otomatik kapatılmadı.",
            price_line,
            f"Sebep kodu: {reason}",
            f"Not: {LEGAL_NOTE}",
        ]
    )
    assert_language_safe(text)
    return text


def build_no_trade_card(
    *, as_of_utc: str, regime_line: str, blockers: list[str], data_health: str
) -> str:
    """P2-1: 'sinyal yok' birinci sınıf çıktıdır — sessizlik bilgi değildir."""
    lines = [
        f"[DURUM] {as_of_utc} UTC · yeni yönsel sinyal üretilmedi",
        f"Rejim: {regime_line}",
        "Mevcut engeller: " + ("; ".join(blockers) if blockers else "yok — tetik koşulu oluşmadı"),
        f"Veri sağlığı: {data_health}",
        f"Not: {LEGAL_NOTE}",
    ]
    text = "\n".join(lines)
    assert_language_safe(text)
    return text
