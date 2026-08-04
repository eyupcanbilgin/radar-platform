"""CLI script to evaluate decision outcomes (+1h, +4h, +24h) for recorded decisions."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.evaluator import HourlyOutcomeEvaluator, load_cost_config  # noqa: E402
from decision_engine.ledger import DecisionLedger  # noqa: E402
from decision_engine.sources import BinanceUsdMClosedCandleSource, require_utc_hour  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BTC 1h Decision Outcome Evaluator CLI")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=SERVICE_ROOT / "var" / "decision_ledger.sqlite",
        help="Path to decision ledger SQLite file",
    )
    parser.add_argument(
        "--max-decisions",
        type=int,
        default=50,
        help="Maximum number of un-evaluated decisions to process (default: 50)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Specific decision as_of_utc ISO string to evaluate (e.g. 2026-08-04T12:00:00Z)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = args.db_path
    if not db_path.exists():
        print(f"Decision ledger database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    ledger = DecisionLedger(db_path)
    candle_source = BinanceUsdMClosedCandleSource()
    cost_config = load_cost_config()
    evaluator = HourlyOutcomeEvaluator(
        ledger=ledger,
        candle_source=candle_source,
        cost_config=cost_config,
    )

    if args.as_of:
        as_of = require_utc_hour(datetime.fromisoformat(args.as_of.replace("Z", "+00:00")))
        record = ledger.get_for_period(as_of_utc=as_of)
        if not record:
            print(f"No decision found for as_of={as_of.isoformat()}", file=sys.stderr)
            sys.exit(1)
        decision_ids = [record["decision_id"]]
    else:
        # Find decisions that lack +1h, +4h, or +24h outcomes
        cursor = ledger._conn.execute(
            """
            SELECT d.decision_id FROM hourly_decisions d
            LEFT JOIN (
                SELECT decision_id, COUNT(*) AS outcome_count
                FROM decision_outcomes GROUP BY decision_id
            ) o ON d.decision_id = o.decision_id
            WHERE o.outcome_count IS NULL OR o.outcome_count < 3
            ORDER BY d.as_of_utc ASC
            LIMIT ?
            """,
            (args.max_decisions,),
        )
        decision_ids = [row["decision_id"] for row in cursor.fetchall()]

    if not decision_ids:
        print("No pending decisions require outcome evaluation.")
        return

    print(f"Evaluating outcomes for {len(decision_ids)} decisions...")
    evaluated_count = 0
    for decision_id in decision_ids:
        try:
            outcomes = evaluator.evaluate_decision(decision_id)
            evaluated_count += len(outcomes)
            for outcome in outcomes:
                print(
                    f"Decision {decision_id} | {outcome.horizon} | Status: {outcome.status} | "
                    f"Decision: {outcome.decision_outcome} | Raw: {outcome.raw_return} | "
                    f"Net: {outcome.net_return} | Opp: {outcome.opportunity_return}"
                )
        except Exception as error:
            print(f"Error evaluating decision {decision_id}: {error}", file=sys.stderr)

    print(f"Finished evaluation. Total outcomes processed: {evaluated_count}.")


if __name__ == "__main__":
    main()
