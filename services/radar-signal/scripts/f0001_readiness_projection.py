"""Project when F-0001 can actually be measured — from the ledger, without reading outcomes.

`f0001_forward_coverage.py` answers "where are we?".  This answers "when, at the rate we are
actually going?", which is the question the product owner keeps asking and which nobody in
this repo could answer with evidence.

Why it matters: the observation counter is **not** the binding constraint. The pre-registered
thresholds interact in a way that is easy to miss:

- `trigger.min_observations = 720` (30 hours×days) and
- `validation.min_triggered_events_per_venue = 30`, while
- `trigger.episode_cooldown_hours = 24` caps triggers at **one per day**.

So 720 observations can yield **at most 30 triggers**, and only if a trigger fires every
single day.  The historical readiness run (ADR-0029) measured 10 independent triggers from
1 743 usable contexts — roughly one per 7 days.  At that rate the trigger requirement, not
the observation requirement, decides the date.

Two honesty rules are load-bearing:

- **A rate estimated from too few observations is not reported as a date.**  Three
  observations and zero triggers cannot produce a forecast; the report says
  `insufficient_sample` instead of inventing one.
- **Historical rates are labelled historical.**  They are a reference for what the forward
  rate might look like, never presented as the forward measurement.

This tool reads no outcomes, writes no Registry row, and produces no direction.
"""

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
CALIBRATION_PATH = SERVICE_ROOT / "config" / "fragility_calibration.yaml"

#: Bir oranı takvim tarihine çevirmek için gereken en az gözlem. Bunun altında oran
#: raporlanır ama TARİH raporlanmaz: 3 gözlemden çıkarılmış bir tarih uydurmadır.
MIN_OBSERVATIONS_FOR_RATE = 48

#: ADR-0029'un mühürlü ana context setinde ölçtüğü tarihsel epizot oranı. Forward ölçüm
#: DEĞİLDİR; forward oran hesaplanamadığında referans olarak, açıkça etiketli sunulur.
HISTORICAL_REFERENCE = {
    "source": "Signal ADR-0029 (mühürlü ana context seti)",
    "usable_contexts": 1743,
    "independent_triggers": 10,
}


def _load_calibration() -> dict:
    import yaml

    return yaml.safe_load(CALIBRATION_PATH.read_text(encoding="utf-8"))


def _project(*, current: int, required: int, per_hour_rate: float | None, as_of: datetime) -> dict:
    """Kalan miktarı orana bölüp tarihe çevir; oran yoksa tarih üretme."""
    remaining = max(0, required - current)
    result: dict = {"current": current, "required": required, "remaining": remaining}
    if remaining == 0:
        result["status"] = "met"
        return result
    if not per_hour_rate or per_hour_rate <= 0:
        result["status"] = "insufficient_sample"
        result["eta_utc"] = None
        return result
    hours = remaining / per_hour_rate
    result["status"] = "projected"
    result["projected_hours"] = round(hours, 1)
    result["projected_days"] = round(hours / 24.0, 1)
    result["eta_utc"] = (as_of + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    return result


def build_projection_report(
    *, rows: list[dict], calibration: dict, as_of: datetime, observation_start: datetime
) -> dict:
    """Forward defterinden ölçüm hazırlığı projeksiyonu. Sonuç okumaz, Registry yazmaz."""
    payloads = [row["payload"] for row in rows]
    recorded = len(payloads)
    available = [row for row in payloads if row["status"] != "unavailable"]
    triggered = [row for row in available if row.get("triggered") is True]

    elapsed_hours = max((as_of - observation_start).total_seconds() / 3600.0, 1.0)
    available_rate = len(available) / elapsed_hours
    trigger_rate = len(triggered) / elapsed_hours if len(available) else 0.0

    trigger_cfg = calibration["trigger"]
    validation_cfg = calibration["validation"]
    cooldown_hours = int(trigger_cfg["episode_cooldown_hours"])
    min_observations = int(trigger_cfg["min_observations"])
    min_triggers = int(validation_cfg["min_triggered_events_per_venue"])

    # Yapısal tavan: cooldown, gözlem başına tetik sayısını sınırlar.
    max_triggers_at_min_observations = min_observations // cooldown_hours

    enough_sample = len(available) >= MIN_OBSERVATIONS_FOR_RATE
    observations = _project(
        current=len(available),
        required=min_observations,
        per_hour_rate=available_rate if enough_sample else None,
        as_of=as_of,
    )
    triggers = _project(
        current=len(triggered),
        required=min_triggers,
        per_hour_rate=trigger_rate if enough_sample else None,
        as_of=as_of,
    )

    historical_rate = (
        HISTORICAL_REFERENCE["independent_triggers"] / HISTORICAL_REFERENCE["usable_contexts"]
    )
    historical_reference = {
        **HISTORICAL_REFERENCE,
        "triggers_per_available_hour": round(historical_rate, 6),
        "hours_per_trigger": round(1 / historical_rate, 1),
        "note": "tarihsel referans; forward ölçüm değildir",
    }
    if triggers["status"] != "met":
        remaining = triggers["remaining"]
        historical_reference["projected_available_hours_for_remaining"] = round(
            remaining / historical_rate, 1
        )

    blockers = []
    if observations["status"] != "met":
        blockers.append(f"observations:{observations['current']}/{min_observations}")
    if triggers["status"] != "met":
        blockers.append(f"triggers:{triggers['current']}/{min_triggers}")

    return {
        "schema_version": "f0001-readiness-projection/v1",
        "hypothesis_id": "F-0001",
        "generated_at_utc": as_of.isoformat().replace("+00:00", "Z"),
        "observation_start_utc": observation_start.isoformat().replace("+00:00", "Z"),
        "recorded_observation_count": recorded,
        "available_observation_count": len(available),
        "triggered_observation_count": len(triggered),
        "rate_sample_sufficient": enough_sample,
        "min_observations_for_rate": MIN_OBSERVATIONS_FOR_RATE,
        "requirements": {"observations": observations, "triggers": triggers},
        "structural_ceiling": {
            "episode_cooldown_hours": cooldown_hours,
            "max_triggers_at_min_observations": max_triggers_at_min_observations,
            "required_triggers": min_triggers,
            # 720 saatlik gözlemde cooldown yüzünden en fazla 30 tetik olabilir; şart tam
            # 30 ise gözlem eşiği KARŞILANDIĞINDA bile tetik eşiği ancak her gün tetik
            # olursa karşılanır. Bu, eşiklerin birbirini zorladığını gösterir.
            "requires_trigger_every_cooldown_window": min_triggers
            >= max_triggers_at_min_observations,
        },
        "historical_reference": historical_reference,
        "binding_constraint": (
            "triggers"
            if triggers["status"] != "met" and observations["status"] == "met"
            else "both"
            if blockers and len(blockers) > 1
            else (blockers[0].split(":")[0] if blockers else "none")
        ),
        "blockers": blockers,
        "measurement_ready": not blockers,
        "direction": None,
        "outcome_read": False,
        "registry_write": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, help="raporu atomik JSON olarak yaz")
    parser.add_argument("--now", help="test/replay için sabit UTC an")
    args = parser.parse_args(argv)

    observation_config = load_forward_observation_config()
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00")).astimezone(UTC)
        if args.now
        else datetime.now(UTC)
    )
    start = datetime.fromisoformat(
        observation_config["observation_start_utc"].replace("Z", "+00:00")
    ).astimezone(UTC)

    # Defter tam saat sınırı ister; coverage raporuyla aynı due-saat mantığı kullanılır ki
    # iki rapor aynı kesimi görsün.
    grace = int(observation_config["coverage_grace_seconds"])
    boundary = now.replace(minute=0, second=0, microsecond=0)
    if now < boundary + timedelta(seconds=grace):
        boundary -= timedelta(hours=1)

    with ForwardTriggerLedger(args.ledger, read_only=True) as ledger:
        rows = ledger.observations_through(boundary)

    report = build_projection_report(
        rows=rows, calibration=_load_calibration(), as_of=boundary, observation_start=start
    )
    if args.output:
        atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
