"""Emit outage alerts for the paper runtime; read local state only, never the network.

Periodic one-shot, like ``f0001_forward_coverage.py``: launchd runs it on an interval and it
exits.  It reads the forward coverage report and the MCP heartbeat, decides whether progress
has stopped, and enqueues operator alerts into the SAME outbox the hourly card uses, so the
existing pump delivers them and the existing idempotency protects them.  No parallel
delivery path, no secrets, no direction.

Recovery is detected by comparing against the previous run's atomic status file: that file is
already written every run, so it is the natural state carrier and avoids scanning the outbox.
If the file is lost, a recovery notice is simply skipped — a missed "all clear" is a far
cheaper failure than a missed outage.
"""

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.jsonio import atomic_json  # noqa: E402
from decision_engine.runtime_health import (  # noqa: E402
    ALERT_KIND,
    CONDITION_COVERAGE_LOW,
    CONDITION_FORWARD_STALLED,
    CONDITION_PRODUCER_BEHIND,
    Incident,
    build_report,
    evaluate,
    load_alert_config,
    render_alert,
    render_recovery,
)
from enricher.outbox import Outbox  # noqa: E402

DEFAULT_CONFIG = SERVICE_ROOT / "config" / "runtime_health_alert.yaml"
#: Producer yayın grace'i (MCP ADR-0006); due saat bununla hesaplanır.
PUBLISH_GRACE_SECONDS = 90


def _latest_due_hour(now_utc: datetime, *, grace_seconds: int) -> datetime:
    boundary = now_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if now_utc.astimezone(UTC) < boundary + timedelta(seconds=grace_seconds):
        boundary -= timedelta(hours=1)
    return boundary


def _read_coverage(path: Path, errors: list[str]) -> str | None:
    """Son forward gözlem saatini oku. Okunamıyorsa sessiz geçme, hatayı bildir."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"coverage raporu yok: {path}")
        return None
    except (OSError, ValueError) as error:
        errors.append(f"coverage raporu okunamadı: {type(error).__name__}")
        return None
    if not isinstance(payload, dict):
        errors.append("coverage raporu beklenen yapıda değil")
        return None
    return payload.get("last_observation_utc")


def _read_producer_publish(path: Path | None, errors: list[str]) -> str | None:
    """MCP heartbeat'ten son BAŞARILI publish saatini oku (ağa çıkmaz)."""
    if path is None:
        return None
    if not path.is_file():
        errors.append(f"producer heartbeat yok: {path}")
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT as_of FROM heartbeats "
                "WHERE task='publish' AND status='ok' AND as_of IS NOT NULL "
                "ORDER BY as_of DESC LIMIT 1"
            ).fetchone()
    except sqlite3.Error as error:
        errors.append(f"producer heartbeat okunamadı: {type(error).__name__}")
        return None
    return row[0] if row else None


def _read_recent_forward_hours(path: Path | None, since_utc: datetime, errors: list[str]):
    """Pencere içinde forward gözlemi taşıyan DISTINCT saat sayısı (ağa çıkmaz, salt-okunur).

    Yetkili kaynak defterin kendisidir; coverage raporu üzerinden okumak, rapor bayatladığında
    sağlığı bayat sayılarla "iyi" gösterebilirdi.
    """
    if path is None:
        return None
    if not path.is_file():
        errors.append(f"forward defteri yok: {path}")
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT DISTINCT as_of_utc FROM f0001_trigger_observations"
            ).fetchall()
    except sqlite3.Error as error:
        errors.append(f"forward defteri okunamadı: {type(error).__name__}")
        return None
    # Karşılaştırma metinde değil zamanda yapılır: defterde bir satır `Z` ekiyle yazılmış
    # olsaydı metin sıralaması onu sessizce pencerenin dışında sayardı. Defter saat başına
    # bir satırdır; tam tarama ölçekte sorun değildir.
    count = 0
    for (value,) in rows:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"forward defterinde ayrıştırılamayan saat: {value!r}")
            return None
        if parsed.tzinfo is None:
            errors.append(f"forward defterinde timezone'suz saat: {value!r}")
            return None
        if parsed.astimezone(UTC) >= since_utc:
            count += 1
    return count


def _previous_incidents(path: Path) -> list[Incident]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload["active_incidents"]
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    restored: list[Incident] = []
    for item in items:
        try:
            restored.append(
                Incident(
                    condition=item["condition"],
                    since_utc=item["since_utc"],
                    gap_hours=int(item["gap_hours"]),
                    detail=str(item["detail"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return restored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True, help="forward coverage JSON")
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True, help="atomik son durum")
    parser.add_argument("--producer-heartbeat", type=Path, default=None)
    parser.add_argument(
        "--f0001-trigger-ledger",
        type=Path,
        default=None,
        help="forward defteri; pencere kapsama oranı buradan ölçülür (ADR-0051)",
    )
    parser.add_argument(
        "--observation-start-utc",
        default=None,
        help="pencere bu andan öncesine uzatılmaz; kurulum öncesi saatler doldurulamaz",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--now", help="test/replay için sabit UTC an")
    args = parser.parse_args(argv)

    try:
        config = load_alert_config(args.config)
        now = (
            datetime.fromisoformat(args.now.replace("Z", "+00:00")).astimezone(UTC)
            if args.now
            else datetime.now(UTC)
        )
        latest_due = _latest_due_hour(now, grace_seconds=PUBLISH_GRACE_SECONDS)

        errors: list[str] = []
        last_forward = _read_coverage(args.coverage, errors)
        published = _read_producer_publish(args.producer_heartbeat, errors)
        window_start = latest_due - timedelta(hours=config["window_hours"] - 1)
        observation_start = (
            datetime.fromisoformat(args.observation_start_utc.replace("Z", "+00:00")).astimezone(
                UTC
            )
            if args.observation_start_utc
            else None
        )
        if observation_start is not None:
            window_start = max(window_start, observation_start)
        recent_hours = _read_recent_forward_hours(args.f0001_trigger_ledger, window_start, errors)

        incidents = evaluate(
            now_utc=now,
            latest_due_utc=latest_due,
            last_forward_observation_utc=last_forward,
            producer_published_as_of_utc=published,
            config=config,
            read_errors=errors,
            recent_forward_hours=recent_hours,
            observation_start_utc=observation_start,
        )

        previous = _previous_incidents(args.status_output)
        active_keys = {(item.condition, item.since_utc) for item in incidents}
        emitted: list[dict] = []
        recovered: list[dict] = []

        with Outbox(args.outbox) as outbox:
            for incident in incidents:
                signal_id = incident.signal_id(config["escalation_hours"])
                created = outbox.enqueue(
                    signal_id=signal_id,
                    kind=ALERT_KIND,
                    body=render_alert(
                        incident, now_utc=now, escalation_hours=config["escalation_hours"]
                    ),
                    now=now,
                )
                emitted.append(
                    {
                        "signal_id": signal_id,
                        "condition": incident.condition,
                        "gap_hours": incident.gap_hours,
                        "bucket_hours": incident.bucket(config["escalation_hours"]),
                        # False = aynı kesinti+eşik için zaten uyarılmış; tekrar gönderilmez.
                        "created": created,
                    }
                )
            for stale in previous:
                if (stale.condition, stale.since_utc) in active_keys:
                    continue
                if stale.condition not in (
                    CONDITION_FORWARD_STALLED,
                    CONDITION_PRODUCER_BEHIND,
                    CONDITION_COVERAGE_LOW,
                ):
                    continue
                signal_id = stale.recovery_signal_id()
                created = outbox.enqueue(
                    signal_id=signal_id,
                    kind=ALERT_KIND,
                    body=render_recovery(stale),
                    now=now,
                )
                recovered.append(
                    {
                        "signal_id": signal_id,
                        "condition": stale.condition,
                        "since_utc": stale.since_utc,
                        "created": created,
                    }
                )

        report = build_report(
            now_utc=now,
            latest_due_utc=latest_due,
            incidents=incidents,
            emitted=emitted,
            recovered=recovered,
        )
        atomic_json(args.status_output, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:  # izleyici ham traceback değil, makine-okunur kayıt bırakır
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(error).__name__,
                    "error": " ".join(str(error).split())[:400],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
