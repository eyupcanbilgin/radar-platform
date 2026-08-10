"""Outage detection for the paper runtime: alert when progress stops, not when data is thin.

Why this exists: on 2026-08-10 the forward ledger had been frozen since 2026-08-09T22:00Z —
roughly seventeen hours — while all four launchd agents reported ``running``.  Nothing said
anything.  ``running`` is not evidence of health, and a silent stall costs exactly the
forward evidence the whole phase is waiting on (Signal ADR-0041, ADR-0042).

The central design decision is what NOT to alert on.  Coverage ``status`` is permanently
``degraded`` because the hours before runtime installation can never be filled; wiring an
alert to it would fire on every single run and train the operator to ignore alerts.  So this
module watches **progress**, not **state**: has the forward ledger advanced, is the producer
publishing the hour it should.

Two honesty rules are load-bearing:

- **Silence is never healthy.**  If an input cannot be read, that is itself an alert
  (``inputs_unreadable``), never a quiet "ok".  A monitor's worst act is reporting health it
  did not verify (MCP ADR-0006 §8).
- **A late alert must not understate the outage.**  This agent cannot run while the host
  sleeps, so an alert may surface long after the stall began.  Every alert therefore carries
  the observed gap and the last known-good hour rather than "just noticed" wording.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

SCHEMA_VERSION = "runtime-health/v1"
ALERT_KIND = "runtime_health_alert"

CONDITION_FORWARD_STALLED = "forward_stalled"
CONDITION_PRODUCER_BEHIND = "producer_behind"
CONDITION_INPUTS_UNREADABLE = "inputs_unreadable"


class RuntimeHealthConfigError(ValueError):
    """The operational thresholds are missing or unusable."""


def load_alert_config(path: Path) -> dict:
    """Load and fail-loud validate the operational thresholds."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != "1":
        raise RuntimeHealthConfigError("runtime_health_alert config version=1 olmalı")
    try:
        stall_hours = raw["forward_stall"]["stall_hours"]
        max_behind = raw["producer_publish"]["max_hours_behind"]
        escalation = raw["escalation_hours"]
    except (KeyError, TypeError) as error:
        raise RuntimeHealthConfigError(f"eksik eşik alanı: {error}") from error
    for name, value in (("stall_hours", stall_hours), ("max_hours_behind", max_behind)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RuntimeHealthConfigError(f"{name} >= 1 tam sayı olmalı")
    if (
        not isinstance(escalation, list)
        or not escalation
        or any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in escalation)
        or sorted(set(escalation)) != escalation
    ):
        raise RuntimeHealthConfigError("escalation_hours artan, tekrarsız, pozitif liste olmalı")
    return {
        "stall_hours": stall_hours,
        "max_hours_behind": max_behind,
        "escalation_hours": list(escalation),
    }


@dataclass(frozen=True)
class Incident:
    """One ongoing outage, identified by what was last known good."""

    condition: str
    since_utc: str
    gap_hours: int
    detail: str

    def bucket(self, escalation_hours: list[int]) -> int:
        """Highest crossed escalation step; alerts fire once per step, not per run."""
        crossed = [step for step in escalation_hours if self.gap_hours >= step]
        return crossed[-1] if crossed else escalation_hours[0]

    def signal_id(self, escalation_hours: list[int]) -> str:
        digest = hashlib.sha256(
            f"{self.condition}|{self.since_utc}|{self.bucket(escalation_hours)}".encode()
        ).hexdigest()
        return f"OPS-{digest[:16]}"

    def recovery_signal_id(self) -> str:
        digest = hashlib.sha256(f"{self.condition}|{self.since_utc}|recovered".encode()).hexdigest()
        return f"OPS-{digest[:16]}"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware UTC bekleniyor")
    return parsed.astimezone(UTC)


def _whole_hours(delta: timedelta) -> int:
    return int(delta.total_seconds() // 3600)


def evaluate(
    *,
    now_utc: datetime,
    latest_due_utc: datetime,
    last_forward_observation_utc: str | None,
    producer_published_as_of_utc: str | None,
    config: dict,
    read_errors: list[str],
) -> list[Incident]:
    """Return every active incident.  An empty list means progress is being made.

    ``read_errors`` is not an internal detail: an input we failed to read becomes its own
    incident so an unreadable state can never be reported as healthy.
    """
    if now_utc.tzinfo is None or latest_due_utc.tzinfo is None:
        raise ValueError("now_utc ve latest_due_utc timezone-aware olmalı")
    incidents: list[Incident] = []

    if read_errors:
        incidents.append(
            Incident(
                condition=CONDITION_INPUTS_UNREADABLE,
                since_utc=now_utc.isoformat().replace("+00:00", "Z"),
                gap_hours=0,
                detail="; ".join(sorted(read_errors))[:400],
            )
        )
        # Okunamayan girdiden ilerleme çıkarımı yapılmaz; sessizce "sağlıklı" demeyiz.
        return incidents

    if last_forward_observation_utc is None:
        incidents.append(
            Incident(
                condition=CONDITION_FORWARD_STALLED,
                since_utc=latest_due_utc.isoformat().replace("+00:00", "Z"),
                gap_hours=0,
                detail="forward defterinde hiç gözlem yok",
            )
        )
    else:
        last_observed = _parse_utc(last_forward_observation_utc)
        gap = _whole_hours(latest_due_utc - last_observed)
        if gap >= config["stall_hours"]:
            incidents.append(
                Incident(
                    condition=CONDITION_FORWARD_STALLED,
                    since_utc=last_observed.isoformat().replace("+00:00", "Z"),
                    gap_hours=gap,
                    detail=(
                        f"son forward gözlemi {last_forward_observation_utc}; "
                        f"beklenen due saat {latest_due_utc.isoformat().replace('+00:00', 'Z')}"
                    ),
                )
            )

    if producer_published_as_of_utc is not None:
        published = _parse_utc(producer_published_as_of_utc)
        behind = _whole_hours(latest_due_utc - published)
        if behind > config["max_hours_behind"]:
            incidents.append(
                Incident(
                    condition=CONDITION_PRODUCER_BEHIND,
                    since_utc=published.isoformat().replace("+00:00", "Z"),
                    gap_hours=behind,
                    detail=(
                        f"producer son yayını {producer_published_as_of_utc}; "
                        f"due {latest_due_utc.isoformat().replace('+00:00', 'Z')}"
                    ),
                )
            )
    return incidents


def render_alert(incident: Incident, *, now_utc: datetime, escalation_hours: list[int]) -> str:
    """Deterministic operator text.  Same incident+bucket must render byte-identically.

    The outbox rejects a reused idempotency key with a different body, so the rendered text
    may only contain fields that also feed ``signal_id``.  ``now`` is deliberately absent.
    """
    bucket = incident.bucket(escalation_hours)
    return "\n".join(
        [
            f"[RADAR OPERASYON] {incident.condition}",
            f"Son bilinen sağlıklı an: {incident.since_utc}",
            f"Gözlenen boşluk: {incident.gap_hours} saat (eşik: {bucket} saat)",
            f"Ayrıntı: {incident.detail}",
            "",
            "Bu bir piyasa sinyali DEĞİLDİR: yön, skor veya işlem önerisi içermez.",
            "Uyarı yerel izlemeden gelir; host uykudayken ajan da koşmaz, bu yüzden uyarı",
            "kesintinin başlangıcından sonra ortaya çıkmış olabilir. Yukarıdaki boşluk",
            "gerçek gözlenen boşluktur, uyarının yaşı değildir.",
        ]
    )


def render_recovery(incident: Incident) -> str:
    return "\n".join(
        [
            f"[RADAR OPERASYON] {incident.condition} — ilerleme geri döndü",
            f"Kesintinin başladığı an: {incident.since_utc}",
            f"Kapanan boşluk: {incident.gap_hours} saat",
            "",
            "Eksik saatler geriye dönük doldurulmaz; blocker olarak kalır.",
            "Bu bir piyasa sinyali DEĞİLDİR.",
        ]
    )


def build_report(
    *,
    now_utc: datetime,
    latest_due_utc: datetime,
    incidents: list[Incident],
    emitted: list[dict],
    recovered: list[dict],
) -> dict:
    """Atomic last-state file.  Also the carrier that lets the next run detect recovery."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "latest_due_utc": latest_due_utc.isoformat().replace("+00:00", "Z"),
        "healthy": not incidents,
        "active_incidents": [
            {
                "condition": item.condition,
                "since_utc": item.since_utc,
                "gap_hours": item.gap_hours,
                "detail": item.detail,
            }
            for item in incidents
        ],
        "alerts_emitted": emitted,
        "recoveries_emitted": recovered,
        # Bu araç bir izleyicidir: yön üretmez, sonuç okumaz, Registry'ye yazmaz.
        "direction": None,
        "outcome_read": False,
        "registry_write": False,
    }
