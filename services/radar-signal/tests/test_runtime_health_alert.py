"""Fully synthetic outage-alert tests: no network, no user_data/, no live runtime state."""

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from decision_engine.runtime_health import (
    ALERT_KIND,
    CONDITION_FORWARD_STALLED,
    CONDITION_INPUTS_UNREADABLE,
    CONDITION_PRODUCER_BEHIND,
    Incident,
    RuntimeHealthConfigError,
    evaluate,
    load_alert_config,
    render_alert,
)
from enricher.outbox import Outbox
from scripts import runtime_health_alert as cli

NOW = datetime(2026, 8, 10, 15, 35, tzinfo=UTC)
DUE = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)
CONFIG = {"stall_hours": 2, "max_hours_behind": 1, "escalation_hours": [2, 6, 12, 24, 48]}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _write_config(tmp_path: Path, **overrides) -> Path:
    payload = {
        "version": "1",
        "forward_stall": {"stall_hours": 2},
        "producer_publish": {"max_hours_behind": 1},
        "escalation_hours": [2, 6, 12, 24, 48],
    }
    payload.update(overrides)
    path = tmp_path / "runtime_health_alert.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _write_coverage(tmp_path: Path, last_observation: str | None, **extra) -> Path:
    path = tmp_path / "coverage.json"
    payload = {"last_observation_utc": last_observation, "status": "degraded", **extra}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_heartbeat(tmp_path: Path, published_as_of: str | None) -> Path:
    """Aynı tmp_path'te tekrar çağrılabilir olmalı: CLI testleri iki kez koşuyor."""
    path = tmp_path / "heartbeat.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS heartbeats (task TEXT, status TEXT, as_of TEXT)"
        )
        connection.execute("DELETE FROM heartbeats")
        if published_as_of is not None:
            connection.execute(
                "INSERT INTO heartbeats VALUES ('publish','ok',?)", (published_as_of,)
            )
        connection.commit()
    finally:
        connection.close()
    return path


# --- Ne zaman alarm ÜRETİLMEZ (en önemli kısım) ---------------------------------------


def test_permanently_degraded_coverage_alone_is_not_an_outage():
    """`status=degraded` kurulum öncesi eksik saatler yüzünden KALICIDIR.

    Ona alarm bağlansaydı her koşuda uyarı çıkar ve operatör alarmı görmezden gelmeyi
    öğrenirdi. Alarm duran duruma değil, duran ilerlemeye bakar.
    """
    incidents = evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc=_iso(DUE),  # ilerleme var
        producer_published_as_of_utc=_iso(DUE),
        config=CONFIG,
        read_errors=[],
    )
    assert incidents == []


def test_a_single_missed_hour_is_below_the_stall_threshold():
    incidents = evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc=_iso(DUE - timedelta(hours=1)),
        producer_published_as_of_utc=_iso(DUE),
        config=CONFIG,
        read_errors=[],
    )
    assert incidents == []


# --- Ne zaman alarm ÜRETİLİR ----------------------------------------------------------


def test_the_real_17_hour_outage_would_have_been_caught():
    """10 Ağustos'taki gerçek kesinti: son gözlem 2026-08-09T22:00Z, due 15:00."""
    incidents = evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc="2026-08-09T22:00:00+00:00",
        producer_published_as_of_utc=_iso(DUE),
        config=CONFIG,
        read_errors=[],
    )
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.condition == CONDITION_FORWARD_STALLED
    assert incident.gap_hours == 17
    assert incident.bucket(CONFIG["escalation_hours"]) == 12


def test_producer_falling_behind_is_its_own_incident():
    incidents = evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc=_iso(DUE),
        producer_published_as_of_utc=_iso(DUE - timedelta(hours=4)),
        config=CONFIG,
        read_errors=[],
    )
    assert [item.condition for item in incidents] == [CONDITION_PRODUCER_BEHIND]
    assert incidents[0].gap_hours == 4


def test_unreadable_input_is_an_incident_never_a_silent_ok():
    """Bir izleyicinin yapabileceği en kötü şey, bilmediği için 'sağlıklı' demektir."""
    incidents = evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc=None,
        producer_published_as_of_utc=None,
        config=CONFIG,
        read_errors=["coverage raporu okunamadı: OSError"],
    )
    assert [item.condition for item in incidents] == [CONDITION_INPUTS_UNREADABLE]


# --- Tekrar uyarı üretmeme (idempotency) ----------------------------------------------


def test_same_incident_and_bucket_render_byte_identically():
    """Outbox aynı signal_id'yi farklı gövdeyle reddeder; gövde yalnız id'ye giren
    alanlardan türemelidir. `now` bilinçli olarak metne girmez."""
    incident = Incident(CONDITION_FORWARD_STALLED, "2026-08-09T22:00:00Z", 17, "detay")
    first = render_alert(incident, now_utc=NOW, escalation_hours=CONFIG["escalation_hours"])
    later = render_alert(
        incident, now_utc=NOW + timedelta(hours=3), escalation_hours=CONFIG["escalation_hours"]
    )
    assert first == later


def test_escalation_produces_a_new_alert_only_when_a_step_is_crossed():
    base = "2026-08-09T22:00:00Z"
    steps = CONFIG["escalation_hours"]
    at_6 = Incident(CONDITION_FORWARD_STALLED, base, 6, "d").signal_id(steps)
    at_9 = Incident(CONDITION_FORWARD_STALLED, base, 9, "d").signal_id(steps)
    at_12 = Incident(CONDITION_FORWARD_STALLED, base, 12, "d").signal_id(steps)
    assert at_6 == at_9  # aynı kovada: yeni uyarı yok
    assert at_12 != at_6  # eşik aşıldı: yeni uyarı


# --- Uçtan uca CLI (hepsi tmp_path, gerçek runtime state'e dokunmaz) -------------------


def _run(tmp_path: Path, *, last_observation, published, now=NOW) -> dict:
    code = cli.main(
        [
            "--coverage",
            str(_write_coverage(tmp_path, last_observation)),
            "--outbox",
            str(tmp_path / "outbox.sqlite"),
            "--status-output",
            str(tmp_path / "status.json"),
            "--producer-heartbeat",
            str(_write_heartbeat(tmp_path, published)),
            "--config",
            str(_write_config(tmp_path)),
            "--now",
            _iso(now),
        ]
    )
    assert code == 0
    return json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))


def test_cli_enqueues_once_and_stays_idempotent_on_reruns(tmp_path: Path):
    first = _run(tmp_path, last_observation="2026-08-09T22:00:00+00:00", published=_iso(DUE))
    assert first["healthy"] is False
    assert first["alerts_emitted"][0]["created"] is True
    assert first["direction"] is None
    assert first["registry_write"] is False

    second = _run(tmp_path, last_observation="2026-08-09T22:00:00+00:00", published=_iso(DUE))
    # Aynı kesinti + aynı kova: kuyruğa ikinci kez yazılmaz, alarm fırtınası olmaz.
    assert second["alerts_emitted"][0]["created"] is False

    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        rows = outbox.due(NOW + timedelta(minutes=1))
    assert len([r for r in rows if r["kind"] == ALERT_KIND]) == 1


def test_cli_emits_a_recovery_notice_once_progress_returns(tmp_path: Path):
    _run(tmp_path, last_observation="2026-08-09T22:00:00+00:00", published=_iso(DUE))
    healthy = _run(tmp_path, last_observation=_iso(DUE), published=_iso(DUE))

    assert healthy["healthy"] is True
    assert healthy["active_incidents"] == []
    assert len(healthy["recoveries_emitted"]) == 1
    assert healthy["recoveries_emitted"][0]["condition"] == CONDITION_FORWARD_STALLED
    assert healthy["recoveries_emitted"][0]["created"] is True


def test_cli_reports_unreadable_coverage_instead_of_claiming_health(tmp_path: Path):
    code = cli.main(
        [
            "--coverage",
            str(tmp_path / "yok.json"),
            "--outbox",
            str(tmp_path / "outbox.sqlite"),
            "--status-output",
            str(tmp_path / "status.json"),
            "--config",
            str(_write_config(tmp_path)),
            "--now",
            _iso(NOW),
        ]
    )
    assert code == 0
    report = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert report["healthy"] is False
    assert report["active_incidents"][0]["condition"] == CONDITION_INPUTS_UNREADABLE


def test_alert_body_carries_no_direction_or_trading_language(tmp_path: Path):
    _run(tmp_path, last_observation="2026-08-09T22:00:00+00:00", published=_iso(DUE))
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        body = outbox.due(NOW + timedelta(minutes=1))[0]["body"]
    lowered = body.lower()
    # Kelime sınırıyla ara: "kesinti" içindeki "kesin" yatırım tavsiyesi dili değildir.
    for forbidden in ("long", "short", "al", "sat", "kesin", "yükselir", "düşer"):
        assert re.search(rf"\b{forbidden}\b", lowered) is None, forbidden
    # Feragat metni özgün büyük/küçük hâliyle aranır: Türkçe "İ".lower() birleşik nokta
    # üretir ("DEĞİLDİR" -> "deği̇ldi̇r"), casefold karşılaştırması sessizce kayar.
    assert "piyasa sinyali DEĞİLDİR" in body
    # Geç uyarı kesintiyi küçük göstermemeli: gerçek boşluk metinde durmalı.
    assert "17 saat" in body


# --- Config fail-loud ------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"version": "2"},
        {"escalation_hours": [6, 2]},
        {"escalation_hours": []},
        {"forward_stall": {"stall_hours": 0}},
    ],
)
def test_config_is_fail_loud(tmp_path: Path, override):
    with pytest.raises(RuntimeHealthConfigError):
        load_alert_config(_write_config(tmp_path, **override))
