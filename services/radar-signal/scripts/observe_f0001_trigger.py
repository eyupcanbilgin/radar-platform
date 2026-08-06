"""Append one prospective, outcome-blind F-0001 trigger coverage observation."""

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.forward_trigger import (  # noqa: E402
    ForwardTriggerLedger,
    build_forward_observation,
    load_forward_observation_config,
)
from enricher.decision_context import DecisionContextV1  # noqa: E402
from scripts.fragility_calibration import load_fragility_config  # noqa: E402
from scripts.run_f0001_evidence import _context_set_sha256, _load_context_set  # noqa: E402

DEFAULT_LEDGER = SERVICE_ROOT / "var" / "f0001-forward-triggers.sqlite"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-contexts", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args(argv)

    observation_config = load_forward_observation_config()
    calibration_config = load_fragility_config()
    baseline_hash = _context_set_sha256(args.baseline_contexts)
    if baseline_hash != observation_config["baseline_context_set_sha256"]:
        raise ValueError("forward observation baseline context hash config ile uyuşmuyor")
    baseline = _load_context_set(
        args.baseline_contexts,
        expected_variant=observation_config["baseline_variant"],
        config=calibration_config,
    )
    context = DecisionContextV1.model_validate_json(args.context.read_text(encoding="utf-8"))
    with ForwardTriggerLedger(args.ledger) as ledger:
        existing = ledger.get(context.as_of_utc)
        if existing is not None:
            if existing["context_content_hash"] != context.snapshot.content_hash:
                raise ValueError("aynı saat farklı context ile yeniden gözlenemez")
            print(json.dumps({"recorded": False, **existing["payload"]}, sort_keys=True))
            return 0
        observation = build_forward_observation(
            baseline_contexts=baseline,
            prior_contexts=ledger.contexts(),
            context=context,
            calibration_config=calibration_config,
            observation_config=observation_config,
            previous_as_of_utc=ledger.latest_as_of(),
        )
        recorded = ledger.record(observation, context)
    print(json.dumps({"recorded": recorded, **observation}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
