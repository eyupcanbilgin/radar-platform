"""Render the fragility warning card and gate whether it may leave the ledger at all.

This is the product surface for F-0001: the thing a person actually reads when leverage and
liquidity pressure build up.  It is deliberately built **before** there is enough forward
evidence to publish it, and deliberately wired **behind a closed gate**, so that the first
real trigger does not arrive while the delivery path is still being written in a hurry.

Three refusals are the whole point of this module:

- **It never carries a direction.**  A fragility observation says pressure is building, not
  which way price goes.  `direction` stays `None` and the text says so in words, because a
  card that merely omits direction invites the reader to supply their own.
- **It never speaks for an unavailable observation.**  `status="unavailable"` means the
  feature gate refused to measure; turning that into a card would present missing data as a
  calm market.  Only `observed` + `triggered` produces a card.
- **It stays silent while `emit_alerts` is false.**  The gate lives in
  `config/f0001_forward_observation.yaml`, not in code, and closed is the default.

Idempotency: the card is keyed on `observation_id`, which the append-only trigger ledger
already fixes per decision hour.  Re-running an hour therefore re-renders byte-identical text
and the outbox treats it as a safe repeat.
"""

from datetime import UTC, datetime

FRAGILITY_WARNING_KIND = "fragility_warning"


class FragilityWarningGateError(ValueError):
    """The observation cannot produce a card and the caller asked for one anyway."""


def should_emit(observation: dict, *, emit_alerts: bool) -> tuple[bool, str]:
    """Karar ve gerekçesi: bu gözlem uyarı kartı üretebilir mi?

    Gerekçe her zaman döner — sessiz kalmanın sebebi de kayda değer bir bilgidir.
    """
    if not emit_alerts:
        return False, "alerts_disabled_by_config"
    if observation.get("status") != "observed":
        # Ölçülemeyen saat sakin piyasa değildir; kart üretmek onu öyle gösterirdi.
        return False, f"status_not_observed:{observation.get('status')}"
    if observation.get("triggered") is not True:
        return False, "not_triggered"
    if observation.get("direction") is not None:
        # Yön üreten bir gözlem bu üründe olamaz; sessiz geçmek yerine fail-loud.
        raise FragilityWarningGateError("kırılganlık gözlemi yön taşıyamaz; direction null olmalı")
    return True, "triggered"


def render_fragility_warning(observation: dict) -> str:
    """Deterministik operatör metni; aynı gözlem her zaman aynı gövdeyi üretir.

    Metin yalnız `observation_id`'nin sabitlediği alanlardan türer — outbox aynı anahtarı
    farklı gövdeyle reddeder ve `now` bu yüzden metne girmez.
    """
    percentile = observation.get("trigger_percentile")
    fragility = observation.get("fragility")
    blockers = observation.get("blockers") or []
    lines = [
        "[RADAR KIRILGANLIK UYARISI] BTCUSDT · 1h",
        f"Saat: {observation['as_of_utc']}",
        f"Kırılganlık: {fragility} · geçmiş dağılımdaki yeri: %{percentile}",
        "",
        "Bu bir YÖN sinyali DEĞİLDİR. Fiyatın hangi yöne gideceği hakkında hiçbir iddia",
        "taşımaz; yalnız kaldıraç ve likidite baskısının kendi geçmişine göre yükseldiğini",
        "söyler. LONG/SHORT kararı üretilmemiştir ve üretilmeyecektir.",
        "",
        f"Gözlem: {observation['observation_id']}",
        f"Context: {observation['context_snapshot_id']}",
    ]
    if blockers:
        lines.append(f"Blocker: {'; '.join(blockers)}")
    lines += [
        "",
        "PAPER · gerçek emir gönderilmez · yatırım tavsiyesi değildir.",
        "Karar ve risk tamamen kullanıcıya aittir.",
    ]
    return "\n".join(lines)


def enqueue_fragility_warning(
    observation: dict,
    *,
    outbox,
    emit_alerts: bool,
    now: datetime | None = None,
) -> dict:
    """Kapıyı uygula ve geçerse kartı outbox'a yaz. Sonuç her zaman gerekçesiyle döner."""
    allowed, reason = should_emit(observation, emit_alerts=emit_alerts)
    result = {
        "kind": FRAGILITY_WARNING_KIND,
        "as_of_utc": observation.get("as_of_utc"),
        "observation_id": observation.get("observation_id"),
        "emitted": False,
        "reason": reason,
        # Ürün yüzeyi açılsa bile bu üç alan değişmez.
        "direction": None,
        "outcome_read": False,
        "registry_write": False,
    }
    if not allowed:
        return result
    created = outbox.enqueue(
        signal_id=observation["observation_id"],
        kind=FRAGILITY_WARNING_KIND,
        body=render_fragility_warning(observation),
        now=now or datetime.now(UTC),
    )
    result["emitted"] = True
    # False = aynı saat için zaten kuyruğa alınmış; tekrar gönderilmez.
    result["created"] = created
    return result
