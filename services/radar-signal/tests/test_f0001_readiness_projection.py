"""Fully synthetic tests for the F-0001 readiness projection.

No network, no `user_data/`, no live ledger: rows are built in memory.
"""

from datetime import UTC, datetime, timedelta

from scripts.f0001_readiness_projection import (
    MIN_OBSERVATIONS_FOR_RATE,
    build_projection_report,
)

START = datetime(2026, 8, 7, tzinfo=UTC)

CALIBRATION = {
    "trigger": {"min_observations": 720, "episode_cooldown_hours": 24},
    "validation": {"min_triggered_events_per_venue": 30},
}


def _rows(*, available: int, triggered: int, unavailable: int = 0) -> list[dict]:
    rows = []
    hour = 0
    for index in range(available):
        rows.append(
            {
                "payload": {
                    "as_of_utc": (START + timedelta(hours=hour)).isoformat(),
                    "status": "observed",
                    "triggered": index < triggered,
                }
            }
        )
        hour += 1
    for _ in range(unavailable):
        rows.append(
            {
                "payload": {
                    "as_of_utc": (START + timedelta(hours=hour)).isoformat(),
                    "status": "unavailable",
                    "triggered": None,
                }
            }
        )
        hour += 1
    return rows


def test_too_few_observations_produce_no_date():
    """3 gözlem ve 0 tetikten tarih uydurmak, cevap vermekten kötüdür."""
    report = build_projection_report(
        rows=_rows(available=3, triggered=0),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=3),
        observation_start=START,
    )
    assert report["rate_sample_sufficient"] is False
    assert report["requirements"]["observations"]["status"] == "insufficient_sample"
    assert report["requirements"]["observations"]["eta_utc"] is None
    assert report["requirements"]["triggers"]["eta_utc"] is None
    assert report["measurement_ready"] is False


def test_sufficient_sample_produces_a_date():
    hours = MIN_OBSERVATIONS_FOR_RATE * 2
    report = build_projection_report(
        rows=_rows(available=hours, triggered=4),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=hours),
        observation_start=START,
    )
    assert report["rate_sample_sufficient"] is True
    assert report["requirements"]["observations"]["status"] == "projected"
    assert report["requirements"]["observations"]["eta_utc"] is not None
    assert report["requirements"]["observations"]["projected_days"] > 0


def test_cooldown_ceiling_is_reported():
    """720 saatte 24h cooldown ile en fazla 30 tetik olabilir; şart tam 30."""
    report = build_projection_report(
        rows=_rows(available=10, triggered=0),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=10),
        observation_start=START,
    )
    ceiling = report["structural_ceiling"]
    assert ceiling["max_triggers_at_min_observations"] == 30
    assert ceiling["required_triggers"] == 30
    # Gözlem eşiği karşılansa bile tetik eşiği ancak HER GÜN tetik olursa karşılanır.
    assert ceiling["requires_trigger_every_cooldown_window"] is True


def test_triggers_become_the_binding_constraint_once_observations_are_met():
    report = build_projection_report(
        rows=_rows(available=720, triggered=2),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=720),
        observation_start=START,
    )
    assert report["requirements"]["observations"]["status"] == "met"
    assert report["requirements"]["triggers"]["status"] == "projected"
    assert report["binding_constraint"] == "triggers"


def test_unavailable_observations_do_not_count_toward_the_requirement():
    """Eksik/yetersiz gözlem sakin olay sayılmaz; paydaya da girmez."""
    report = build_projection_report(
        rows=_rows(available=5, triggered=0, unavailable=40),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=45),
        observation_start=START,
    )
    assert report["recorded_observation_count"] == 45
    assert report["available_observation_count"] == 5
    assert report["requirements"]["observations"]["current"] == 5


def test_historical_reference_is_labelled_and_never_presented_as_forward():
    report = build_projection_report(
        rows=_rows(available=3, triggered=0),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=3),
        observation_start=START,
    )
    reference = report["historical_reference"]
    assert "tarihsel referans" in reference["note"]
    assert reference["independent_triggers"] == 10
    assert reference["usable_contexts"] == 1743
    # ~7 günde bir tetik: 1743/10 = 174.3 saat
    assert 170 < reference["hours_per_trigger"] < 180


def test_report_never_reads_outcomes_or_writes_registry():
    report = build_projection_report(
        rows=_rows(available=100, triggered=5),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=100),
        observation_start=START,
    )
    assert report["direction"] is None
    assert report["outcome_read"] is False
    assert report["registry_write"] is False


def test_everything_met_reports_ready():
    report = build_projection_report(
        rows=_rows(available=720, triggered=30),
        calibration=CALIBRATION,
        as_of=START + timedelta(hours=720),
        observation_start=START,
    )
    assert report["measurement_ready"] is True
    assert report["blockers"] == []
    assert report["binding_constraint"] == "none"
