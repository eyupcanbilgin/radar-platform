"""Fully synthetic tests for the fragility warning card and its closed gate.

No network, no `user_data/`, no live ledger. The card is wired but silent by design; these
tests exist so the first real trigger meets finished code instead of a rush.
"""

import re
from datetime import UTC, datetime

import pytest

from decision_engine.fragility_warning import (
    FRAGILITY_WARNING_KIND,
    FragilityWarningGateError,
    enqueue_fragility_warning,
    render_fragility_warning,
    should_emit,
)
from enricher.outbox import Outbox

NOW = datetime(2026, 8, 10, 22, 5, tzinfo=UTC)


def _observation(**overrides) -> dict:
    base = {
        "as_of_utc": "2026-08-10T22:00:00+00:00",
        "observation_id": "FTR-b39acefa1ae36c6f3c17",
        "context_snapshot_id": "SNAP-4d35d947d49f8b34",
        "status": "observed",
        "triggered": True,
        "fragility": 92.0,
        "trigger_percentile": 96.4,
        "direction": None,
        "blockers": [],
    }
    base.update(overrides)
    return base


# --- Kapı: ne zaman SESSİZ kalınır -----------------------------------------------------


def test_config_gate_keeps_the_card_silent_by_default():
    """`emit_alerts` config'de kapalıyken tetiklenmiş gözlem bile yayınlanmaz."""
    allowed, reason = should_emit(_observation(), emit_alerts=False)
    assert allowed is False
    assert reason == "alerts_disabled_by_config"


def test_unavailable_observation_never_becomes_a_card():
    """Ölçülemeyen saat sakin piyasa değildir; kart onu öyle gösterirdi."""
    allowed, reason = should_emit(
        _observation(status="unavailable", triggered=None), emit_alerts=True
    )
    assert allowed is False
    assert reason.startswith("status_not_observed")


def test_untriggered_observation_produces_no_card():
    allowed, reason = should_emit(_observation(triggered=False), emit_alerts=True)
    assert allowed is False
    assert reason == "not_triggered"


def test_an_observation_carrying_direction_is_fail_loud():
    """Yön taşıyan gözlem bu üründe olamaz; sessizce atlamak onu normalleştirirdi."""
    with pytest.raises(FragilityWarningGateError, match="yön taşıyamaz"):
        should_emit(_observation(direction="LONG"), emit_alerts=True)


def test_gate_opens_only_for_a_triggered_observation():
    allowed, reason = should_emit(_observation(), emit_alerts=True)
    assert allowed is True
    assert reason == "triggered"


# --- Kart metni ------------------------------------------------------------------------


def test_card_states_it_is_not_a_direction_signal():
    body = render_fragility_warning(_observation())
    assert "YÖN sinyali DEĞİLDİR" in body
    assert "LONG/SHORT kararı üretilmemiştir" in body


def test_card_carries_no_trading_language_outside_its_own_denial():
    """`LONG/SHORT` yalnız "üretilmemiştir" cümlesinde geçebilir, başka hiçbir yerde.

    Feragat metnini taramaya dahil etmek kartın kendi reddini ihlal sanırdı; bu yüzden o
    satırlar çıkarılıp GERİ KALAN metin taranır.
    """
    body = render_fragility_warning(_observation())
    denial = "LONG/SHORT kararı üretilmemiştir ve üretilmeyecektir."
    assert denial in body

    remainder = body.replace(denial, "").lower()
    for forbidden in ("long", "short", "al", "sat", "kesin", "yükselir", "düşer", "hedef"):
        # Kelime sınırı: "kısa"/"satır" gibi masum kelimeler yakalanmasın.
        assert re.search(rf"\b{forbidden}\b", remainder) is None, forbidden


def test_card_is_deterministic_for_the_same_observation():
    """Outbox aynı anahtarı farklı gövdeyle reddeder; `now` metne girmemeli."""
    assert render_fragility_warning(_observation()) == render_fragility_warning(_observation())


def test_card_shows_blockers_when_present():
    body = render_fragility_warning(_observation(blockers=["feature_unavailable:oi_buildup"]))
    assert "feature_unavailable:oi_buildup" in body


# --- Outbox entegrasyonu ---------------------------------------------------------------


def test_silent_gate_writes_nothing_to_the_outbox(tmp_path):
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        result = enqueue_fragility_warning(
            _observation(), outbox=outbox, emit_alerts=False, now=NOW
        )
        assert result["emitted"] is False
        assert result["reason"] == "alerts_disabled_by_config"
        assert outbox.due(NOW) == []


def test_open_gate_enqueues_once_and_stays_idempotent(tmp_path):
    observation = _observation()
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        first = enqueue_fragility_warning(observation, outbox=outbox, emit_alerts=True, now=NOW)
        second = enqueue_fragility_warning(observation, outbox=outbox, emit_alerts=True, now=NOW)

        assert first["emitted"] is True and first["created"] is True
        # Aynı saat ikinci kez kuyruğa alınmaz.
        assert second["created"] is False
        rows = [row for row in outbox.due(NOW) if row["kind"] == FRAGILITY_WARNING_KIND]
        assert len(rows) == 1
        assert "YÖN sinyali DEĞİLDİR" in rows[0]["body"]


def test_result_always_reports_the_product_invariants(tmp_path):
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        for emit in (False, True):
            result = enqueue_fragility_warning(
                _observation(), outbox=outbox, emit_alerts=emit, now=NOW
            )
            assert result["direction"] is None
            assert result["outcome_read"] is False
            assert result["registry_write"] is False
            assert result["kind"] == FRAGILITY_WARNING_KIND
