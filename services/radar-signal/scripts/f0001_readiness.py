"""Report F-0001 context/trigger readiness without opening Locked OOS or writing Registry."""

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.context_sets import (  # noqa: E402
    EXPECTED_EXCLUSIONS,
    context_set_sha256,
    load_context_set,
)
from decision_engine.jsonio import atomic_json  # noqa: E402
from scripts.fragility_calibration import load_fragility_config  # noqa: E402
from scripts.fragility_event_rows import build_trigger_rows  # noqa: E402


def _variant_readiness(contexts: list[dict], config: dict) -> dict:
    usable = [row for row in contexts if row["snapshot"].get("fragility") is not None]
    trigger_rows = build_trigger_rows(contexts, config)
    triggered = sum(bool(row["triggered"]) for row in trigger_rows)
    minimum = int(config["validation"]["min_triggered_events_per_venue"])
    blockers = []
    if not trigger_rows:
        blockers.append("trigger_history_unavailable")
    if triggered < minimum:
        blockers.append(f"insufficient_triggered_events:{triggered}<{minimum}")
    return {
        "context_count": len(contexts),
        "usable_fragility_contexts": len(usable),
        "trigger_eligible_contexts": len(trigger_rows),
        "independent_triggered_events": triggered,
        "required_triggered_events_per_venue": minimum,
        "ready": not blockers,
        "blockers": blockers,
    }


def build_readiness_report(
    *, context_sets: dict[str, list[dict]], context_set_sha256: dict[str, str], config: dict
) -> dict:
    expected = set(EXPECTED_EXCLUSIONS)
    if set(context_sets) != expected or set(context_set_sha256) != expected:
        raise ValueError(f"F-0001 readiness üç variant ister: {sorted(expected)}")
    reports = {
        variant: _variant_readiness(context_sets[variant], config) for variant in sorted(expected)
    }
    blockers = [
        f"{variant}:{blocker}"
        for variant, report in reports.items()
        for blocker in report["blockers"]
    ]
    return {
        "schema_version": "f0001-readiness/v1",
        "hypothesis_id": "F-0001",
        "direction": None,
        "locked_oos_opened": False,
        "locked_oos_start_utc": config["boundaries"]["locked_oos_start_utc"],
        "measurement_ready": not blockers,
        "blockers": blockers,
        "context_set_sha256": context_set_sha256,
        "variants": reports,
        "registry_write": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--contexts-without-funding", type=Path, required=True)
    parser.add_argument("--contexts-without-oi", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    config = load_fragility_config()
    paths = {
        "combined": args.contexts,
        "without_funding_stress": args.contexts_without_funding,
        "without_oi_buildup": args.contexts_without_oi,
    }
    report = build_readiness_report(
        context_sets={
            variant: load_context_set(path, expected_variant=variant, config=config)
            for variant, path in paths.items()
        },
        context_set_sha256={variant: context_set_sha256(path) for variant, path in paths.items()},
        config=config,
    )
    if args.output:
        atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
