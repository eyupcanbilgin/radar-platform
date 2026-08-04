"""Boundedly repair hourly DecisionLedger entries missing from the delivery outbox."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.delivery import HourlyDecisionDelivery  # noqa: E402
from decision_engine.ledger import DecisionLedger  # noqa: E402
from enricher.outbox import Outbox  # noqa: E402
from enricher.policy import load_lifecycle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    db_dir = Path(os.getenv("RADAR_SIGNAL_DB_DIR", SERVICE_ROOT / "var"))
    parser.add_argument("--ledger", type=Path, default=db_dir / "hourly-decisions.sqlite")
    parser.add_argument("--outbox", type=Path, default=db_dir / "outbox.sqlite")
    parser.add_argument("--limit", type=int, default=48, help="en yeni kaç karar taranacak")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit en az 1 olmalı")

    config = load_lifecycle()["outbox"]
    with (
        DecisionLedger(args.ledger) as ledger,
        Outbox(
            args.outbox,
            max_attempts=int(config["max_attempts"]),
            backoff_seconds=list(config["retry_backoff_seconds"]),
            late_delivery_after_minutes=int(config["late_delivery_after_minutes"]),
        ) as outbox,
    ):
        stats = HourlyDecisionDelivery(ledger=ledger, outbox=outbox).reconcile(
            limit=args.limit, now=datetime.now(UTC)
        )
    print(json.dumps(stats, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
