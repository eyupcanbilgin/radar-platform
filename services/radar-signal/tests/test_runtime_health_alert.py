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
    CONDITION_COVERAGE_LOW,
    CONDITION_FORWARD_STALLED,
    CONDITION_INPUTS_UNREADABLE,
    CONDITION_PRODUCER_BEHIND,
    CONDITION_PRODUCER_FAILING,
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
CONFIG = {
    "stall_hours": 2,
    "max_hours_behind": 1,
    "window_hours": 12,
    "min_ratio": 0.75,
    "min_consecutive_failures": 3,
    "escalation_hours": [2, 6, 12, 24, 48],
}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _write_config(tmp_path: Path, **overrides) -> Path:
    payload = {
        "version": "1",
        "forward_stall": {"stall_hours": 2},
        "producer_publish": {"max_hours_behind": 1},
        "forward_coverage": {"window_hours": 12, "min_ratio": 0.75},
        "producer_failure": {"min_consecutive_failures": 3},
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


def _write_heartbeat(
    tmp_path: Path, published_as_of: str | None, *, failures: list[tuple] | None = None
) -> Path:
    """Aynı tmp_path'te tekrar çağrılabilir olmalı: CLI testleri iki kez koşuyor.

    Şema gerçek `HeartbeatStore` ile aynı kolonları taşır: `detail` olmadan kesintinin
    SEBEBİ okunamaz ve bu sütun tam olarak bugün eksik olan bilgiydi.
    """
    path = tmp_path / "heartbeat.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS heartbeats ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, status TEXT, "
            "as_of TEXT, finished_at TEXT, detail TEXT)"
        )
        connection.execute("DELETE FROM heartbeats")
        if published_as_of is not None:
            connection.execute(
                "INSERT INTO heartbeats (task, status, as_of, finished_at, detail) "
                "VALUES ('publish','ok',?,?,'{}')",
                (published_as_of, published_as_of),
            )
        for task, finished_at, error_type, message in failures or []:
            connection.execute(
                "INSERT INTO heartbeats (task, status, as_of, finished_at, detail) "
                "VALUES (?,'error',NULL,?,?)",
                (
                    task,
                    finished_at,
                    json.dumps({"error_type": error_type, "error": message}),
                ),
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


# --- ADR-0051: yavaş kesinti — anlık boşluk değil, pencere ORANI --------------------------

OBSERVATION_START = datetime(2026, 8, 7, tzinfo=UTC)


def _evaluate_coverage(recent_hours, *, due=DUE, start=OBSERVATION_START, config=CONFIG):
    return evaluate(
        now_utc=NOW,
        latest_due_utc=due,
        last_forward_observation_utc=_iso(due),  # anlık boşluk YOK
        producer_published_as_of_utc=_iso(due),  # producer da geride DEĞİL
        config=config,
        read_errors=[],
        recent_forward_hours=recent_hours,
        observation_start_utc=start,
    )


def test_the_slow_outage_that_both_instantaneous_checks_missed():
    """11 Ağu 2026'nın gerçek tablosu: 12 saatin 4'ü kaydedilmiş, iki eşik de sessiz.

    `forward_stalled` ve `producer_behind` o anda temiz: son gözlem ve son yayın due saatin
    kendisi. Yine de runtime saatlerin üçte ikisini kaybediyor.
    """
    incidents = _evaluate_coverage(4)

    assert [item.condition for item in incidents] == [CONDITION_COVERAGE_LOW]
    assert incidents[0].gap_hours == 8
    assert "4" in incidents[0].detail and "12" in incidents[0].detail


def test_a_runtime_at_the_floor_is_not_an_incident():
    """Tam eşik (9/12 = 0.75) olay değildir; eşik aşılmadıkça uyarı üretilmez."""
    assert _evaluate_coverage(9) == []


def test_one_hour_below_the_floor_is_an_incident():
    assert [item.condition for item in _evaluate_coverage(8)] == [CONDITION_COVERAGE_LOW]


def test_the_window_never_reaches_before_observation_start():
    """Kurulum öncesi saatler doldurulamaz; onları beklentiye katmak kalıcı alarm üretirdi.

    Başlangıçtan yalnız 4 saat sonra pencere 12 değil 5 saattir ve 5/5 tamdır.
    """
    due = OBSERVATION_START + timedelta(hours=4)

    assert _evaluate_coverage(5, due=due) == []


def test_a_ledger_that_cannot_be_read_produces_no_false_healthy_signal():
    """Sayı yoksa oran uydurulmaz; okunamayan girdi zaten `inputs_unreadable` üretir."""
    assert _evaluate_coverage(None) == []


def test_more_rows_than_hours_cannot_manufacture_health():
    """Beklenenden çok satır oranı 1'in üstüne çıkarmaz; olay yokluğu doğru kalır."""
    assert _evaluate_coverage(99) == []


def test_the_incident_is_keyed_on_the_window_so_it_does_not_respam_each_run():
    first = _evaluate_coverage(4)[0]
    second = _evaluate_coverage(4)[0]

    assert first.signal_id(CONFIG["escalation_hours"]) == second.signal_id(
        CONFIG["escalation_hours"]
    )


def test_config_rejects_a_ratio_outside_the_unit_interval(tmp_path: Path):
    path = _write_config(tmp_path, forward_coverage={"window_hours": 12, "min_ratio": 1.5})

    with pytest.raises(RuntimeHealthConfigError, match="min_ratio"):
        load_alert_config(path)


def test_config_rejects_a_missing_coverage_block(tmp_path: Path):
    payload = {
        "version": "1",
        "forward_stall": {"stall_hours": 2},
        "producer_publish": {"max_hours_behind": 1},
        "escalation_hours": [2],
    }
    path = tmp_path / "eksik.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(RuntimeHealthConfigError, match="eksik eşik alanı"):
        load_alert_config(path)


def test_the_shipped_config_carries_the_coverage_thresholds():
    config = load_alert_config(Path("config/runtime_health_alert.yaml"))

    assert config["window_hours"] >= 1
    assert 0.0 < config["min_ratio"] <= 1.0


def _ledger(tmp_path: Path, hours: list[datetime]) -> Path:
    path = tmp_path / "f0001.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE f0001_trigger_observations (as_of_utc TEXT)")
        connection.executemany(
            "INSERT INTO f0001_trigger_observations VALUES (?)",
            [(hour,) for hour in hours],
        )
    return path


def test_the_reader_counts_hours_by_time_not_by_string_shape(tmp_path: Path):
    """`Z` ekli bir satır metin sıralamasında pencerenin dışına düşerdi."""
    since = datetime(2026, 8, 10, 4, tzinfo=UTC)
    path = _ledger(
        tmp_path,
        [
            "2026-08-10T04:00:00+00:00",
            "2026-08-10T05:00:00Z",  # aynı pencere, farklı yazım
            "2026-08-10T03:00:00+00:00",  # pencere dışı
        ],
    )
    errors: list[str] = []

    assert cli._read_recent_forward_hours(path, since, errors) == 2
    assert errors == []


def test_an_unparseable_hour_is_reported_instead_of_silently_undercounted(tmp_path: Path):
    path = _ledger(tmp_path, ["bozuk"])
    errors: list[str] = []

    assert cli._read_recent_forward_hours(path, datetime(2026, 8, 10, tzinfo=UTC), errors) is None
    assert errors and "ayrıştırılamayan" in errors[0]


def test_a_missing_ledger_is_an_error_not_a_zero(tmp_path: Path):
    errors: list[str] = []

    result = cli._read_recent_forward_hours(
        tmp_path / "yok.sqlite", datetime(2026, 8, 10, tzinfo=UTC), errors
    )

    assert result is None
    assert errors and "forward defteri yok" in errors[0]


# --- ADR-0053: tekrar eden özdeş hata geçici değildir --------------------------------------

SAMPLING_MODE_ERROR = (
    "1 validation error for SignalRulesConfig collection_metrics.spot_close.sampling_mode "
    "Extra inputs are not permitted"
)


def _failure(consecutive: int, *, error_type: str = "ValidationError", task: str = "collect"):
    return {
        "task": task,
        "consecutive": consecutive,
        "error_type": error_type,
        "error": SAMPLING_MODE_ERROR,
        "since_utc": "2026-08-10T09:00:00Z",
    }


def _evaluate_failure(failure):
    return evaluate(
        now_utc=NOW,
        latest_due_utc=DUE,
        last_forward_observation_utc=_iso(DUE),  # forward duruyor gibi görünmüyor
        producer_published_as_of_utc=_iso(DUE),  # producer geride de değil
        config=CONFIG,
        read_errors=[],
        producer_failure=failure,
    )


def test_the_repeated_schema_error_becomes_an_incident_that_names_the_cause():
    """11 Ağu 2026: 6798 özdeş ValidationError vardı ve hiçbiri alarma ulaşmadı."""
    incidents = _evaluate_failure(_failure(47))

    assert [item.condition for item in incidents] == [CONDITION_PRODUCER_FAILING]
    detail = incidents[0].detail
    assert "47" in detail
    assert "ValidationError" in detail
    assert "sampling_mode" in detail
    assert "sürüm ayrışması" in detail  # operatöre nereye bakacağını söylüyor


def test_a_short_failure_streak_is_not_an_incident():
    """Tek tük ağ hatası kesinti değildir; eşik gürültüyü dışarıda tutar."""
    assert _evaluate_failure(_failure(2)) == []


def test_the_streak_at_the_threshold_fires():
    assert [item.condition for item in _evaluate_failure(_failure(3))] == [
        CONDITION_PRODUCER_FAILING
    ]


def test_no_failure_streak_means_no_incident():
    assert _evaluate_failure(None) == []


def test_the_incident_is_anchored_to_the_start_of_the_outage_not_to_now():
    """Geç fark edilen bir kesinti süresini OLDUĞUNDAN KISA göstermemeli."""
    incident = _evaluate_failure(_failure(47))[0]

    assert incident.since_utc == "2026-08-10T09:00:00Z"
    assert incident.gap_hours == 6  # 09:00 -> 15:00 due


def test_the_reader_counts_only_the_current_streak(tmp_path: Path):
    """Başarıdan ÖNCEKİ eski hatalar sayıya girmez; seri son başarıda kapanır."""
    path = _write_heartbeat(
        tmp_path,
        "2026-08-10T12:00:00Z",
        failures=[
            ("collect", "2026-08-10T14:00:00Z", "ValidationError", SAMPLING_MODE_ERROR),
            ("collect", "2026-08-10T13:00:00Z", "ValidationError", SAMPLING_MODE_ERROR),
        ],
    )
    errors: list[str] = []

    failure = cli._read_producer_failure(path, errors)

    assert failure["task"] == "collect"
    assert failure["consecutive"] == 2
    assert failure["error_type"] == "ValidationError"
    assert errors == []


def test_the_reader_reports_the_worst_task_when_several_are_failing(tmp_path: Path):
    path = _write_heartbeat(
        tmp_path,
        None,
        failures=[
            ("collect", "2026-08-10T14:00:00Z", "ValidationError", SAMPLING_MODE_ERROR),
            ("collect", "2026-08-10T13:00:00Z", "ValidationError", SAMPLING_MODE_ERROR),
            ("collect", "2026-08-10T12:00:00Z", "ValidationError", SAMPLING_MODE_ERROR),
            ("publish", "2026-08-10T14:00:00Z", "ConnectTimeout", "ag hatasi"),
        ],
    )

    failure = cli._read_producer_failure(path, [])

    assert failure["task"] == "collect"
    assert failure["consecutive"] == 3


def test_a_heartbeat_without_a_failure_streak_returns_nothing(tmp_path: Path):
    path = _write_heartbeat(tmp_path, "2026-08-10T14:00:00Z")

    assert cli._read_producer_failure(path, []) is None
