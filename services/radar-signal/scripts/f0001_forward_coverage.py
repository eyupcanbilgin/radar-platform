"""Report outcome-blind F-0001 forward trigger coverage from its immutable ledger."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.forward_trigger import (  # noqa: E402
    ForwardTriggerLedger,
    load_forward_observation_config,
)
from decision_engine.jsonio import atomic_json  # noqa: E402

DEFAULT_LEDGER = SERVICE_ROOT / "var" / "f0001-forward-triggers.sqlite"


def _parse_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or any((parsed.minute, parsed.second, parsed.microsecond)):
        raise ValueError("--as-of timezone-aware UTC saat sınırı olmalı")
    return parsed.astimezone(UTC)


def build_forward_coverage_report(
    *, ledger: ForwardTriggerLedger, observation_config: dict, as_of_utc: datetime
) -> dict:
    """Summarize trigger-ledger coverage without reading outcomes or changing state."""
    as_of_utc = _parse_hour(as_of_utc.isoformat())
    start = _parse_hour(observation_config["observation_start_utc"])
    if as_of_utc < start:
        expected_hours = 0
        rows = []
    else:
        expected_hours = int((as_of_utc - start) / timedelta(hours=1)) + 1
        rows = ledger.observations_through(as_of_utc)

    payloads = [row["payload"] for row in rows]
    if any(_parse_hour(row["as_of_utc"]) < start for row in payloads):
        raise ValueError("forward defterinde ön-kayıt başlangıcından eski gözlem var")
    baseline_hash = observation_config["baseline_context_set_sha256"]
    if any(row["baseline_context_set_sha256"] != baseline_hash for row in payloads):
        raise ValueError("forward defteri baseline hash config ile uyuşmuyor")
    unavailable = sum(row["status"] == "unavailable" for row in payloads)
    triggered = sum(row["triggered"] is True for row in payloads)
    not_triggered = sum(row["triggered"] is False for row in payloads)
    missing = expected_hours - len(rows)
    blockers = []
    if missing:
        blockers.append(f"missing_forward_hours:{missing}")
    if unavailable:
        blockers.append(f"unavailable_forward_observations:{unavailable}")

    return {
        "schema_version": "f0001-forward-coverage/v1",
        "hypothesis_id": "F-0001",
        "as_of_utc": as_of_utc.isoformat().replace("+00:00", "Z"),
        "observation_start_utc": start.isoformat().replace("+00:00", "Z"),
        "baseline_context_set_sha256": baseline_hash,
        "status": "before_start" if expected_hours == 0 else ("degraded" if blockers else "ok"),
        "expected_hour_count": expected_hours,
        "recorded_observation_count": len(rows),
        "missing_hour_count": missing,
        "coverage_ratio": len(rows) / expected_hours if expected_hours else None,
        "available_observation_count": len(rows) - unavailable,
        "unavailable_observation_count": unavailable,
        "triggered_observation_count": triggered,
        "not_triggered_observation_count": not_triggered,
        "first_observation_utc": payloads[0]["as_of_utc"] if payloads else None,
        "last_observation_utc": payloads[-1]["as_of_utc"] if payloads else None,
        "blockers": blockers,
        "direction": None,
        "outcome_read": False,
        "registry_write": False,
        "alert_emitted": False,
    }


def _latest_due_hour(now_utc: datetime, *, grace_seconds: int) -> datetime:
    boundary = now_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if now_utc.astimezone(UTC) < boundary + timedelta(seconds=grace_seconds):
        boundary -= timedelta(hours=1)
    return boundary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--as-of", help="varsayılan son due UTC saati; yalnız rapor kesimi")
    parser.add_argument("--output", type=Path, help="son raporu atomik JSON olarak yaz")
    args = parser.parse_args(argv)
    config = load_forward_observation_config()
    as_of = (
        _parse_hour(args.as_of)
        if args.as_of
        else _latest_due_hour(datetime.now(UTC), grace_seconds=config["coverage_grace_seconds"])
    )
    with ForwardTriggerLedger(args.ledger, read_only=True) as ledger:
        report = build_forward_coverage_report(
            ledger=ledger,
            observation_config=config,
            as_of_utc=as_of,
        )
    if args.output:
        atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
