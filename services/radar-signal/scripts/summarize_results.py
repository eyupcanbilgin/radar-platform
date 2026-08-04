"""Print a compact card-level summary for a pulse-v2 JSON artifact."""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    SERVICE_ROOT / "docs" / "reviews" / "2026-08-04-eleme-v2-draft" / "pulse-v2-results.json"
)


def _format_number(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "NaN"
    return f"{value:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    by_card: dict[str, list[dict]] = defaultdict(list)
    for test in data["tests"]:
        by_card[test["card"]].append(test)

    print(
        f"method={data['method_version']} total={data['total_registered_tests']} "
        f"valid={data['valid_tests']} invalid={data['invalid_tests']}"
    )
    for card, tests in by_card.items():
        directional = [
            test
            for test in tests
            if test["valid"]
            and test["mode"] == "directional"
            and test["alternative"] == "greater"
            and test["beats_cost"]
            and test["sig_fdr_05"]
        ]
        volatility = [
            test
            for test in tests
            if test["valid"]
            and test["mode"] == "volatility_ratio"
            and test["economic_magnitude"]
            and test["sig_fdr_05"]
        ]
        print("\n" + "=" * 72)
        print(f"KART {card}: directional={len(directional)} volatility={len(volatility)}")
        for test in tests:
            print(
                f"  {test['symbol']:>3} {test['horizon']:>6} "
                f"raw/effective={test['raw_n_signals']}/{test['n_signals']} "
                f"effect={test['mean_bps']:>8.2f} "
                f"p={_format_number(test['p_raw'])} "
                f"fdr={_format_number(test['p_fdr'])}"
            )


if __name__ == "__main__":
    main()
