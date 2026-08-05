"""Evaluate Phase-2 statistical gates from a synthetic-or-prepared JSON evidence bundle."""

import argparse
import json
from pathlib import Path

from scripts.registrylib import phase2_trial_count_for_dsr
from scripts.statistical_gates import (
    build_sensitivity_plan,
    evaluate_ablation,
    evaluate_dsr_gate,
    evaluate_pbo_cscv,
    evaluate_sensitivity,
)
from scripts.walk_forward_lib import (
    LockedOOSAccessError,
    load_research_protocol_config,
    parse_utc_datetime,
)


def evaluate_bundle(bundle: dict, *, registry_path: Path | None = None) -> dict:
    config = load_research_protocol_config()
    metadata = bundle.get("metadata", {})
    if metadata.get("scope") != "development":
        raise ValueError("statistical gate bundle scope=development olmalı")
    end = parse_utc_datetime(metadata.get("end_utc", ""))
    if end > config["boundaries"]["locked_oos_start_dt"]:
        raise LockedOOSAccessError("statistical gate bundle Locked OOS sınırını aşamaz")
    gates = config["statistical_gates"]
    required_scenarios = list(gates["required_cost_scenarios"])
    trial_count = phase2_trial_count_for_dsr(registry_path)

    sensitivity_input = bundle["sensitivity"]
    sensitivity_plan = build_sensitivity_plan(
        sensitivity_input["base_parameters"],
        relative_delta=float(gates["sensitivity"]["relative_delta"]),
    )
    reports = {
        "dsr": evaluate_dsr_gate(
            returns_by_trial=bundle["trial_returns"],
            observed_trial_id=bundle["observed_trial_id"],
            registry_trial_count=trial_count,
            confidence_threshold=float(gates["dsr"]["confidence_threshold"]),
        ),
        "pbo_cscv": evaluate_pbo_cscv(
            returns_by_configuration=bundle["configuration_returns"],
            partitions=int(gates["pbo_cscv"]["partitions"]),
            max_combinations=int(gates["pbo_cscv"]["max_combinations"]),
            rejection_threshold=float(gates["pbo_cscv"]["rejection_threshold"]),
        ),
        "sensitivity": evaluate_sensitivity(
            base_metrics=sensitivity_input["base_metrics"],
            variant_metrics=sensitivity_input["variant_metrics"],
            expected_variant_ids=[row["variant_id"] for row in sensitivity_plan],
            required_scenarios=required_scenarios,
            min_retention_ratio=float(gates["sensitivity"]["min_performance_retention_ratio"]),
        ),
        "ablation": evaluate_ablation(
            full_returns=bundle["ablation"]["full_returns"],
            without_family_returns=bundle["ablation"]["without_family_returns"],
            required_scenarios=required_scenarios,
            min_mean_contribution=float(gates["ablation"]["min_mean_contribution"]),
            min_positive_fold_ratio=float(gates["ablation"]["min_positive_fold_ratio"]),
        ),
    }
    return {
        "schema_version": "phase2-statistical-gates/v1",
        "scope": "development",
        "registry_trial_count": trial_count,
        "overall_status": (
            "passed"
            if all(report["status"] == "passed" for report in reports.values())
            else "failed"
        ),
        "reports": reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        bundle = json.loads(args.input.read_text(encoding="utf-8"))
        report = evaluate_bundle(bundle, registry_path=args.registry)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
