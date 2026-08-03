"""Outbox teslimat pompası — ayrı süreç olarak çalışır.

Telegram yapılandırılmışsa oraya, değilse konsola teslim eder. Kesintide mesaj
kaybolmaz: outbox kuyrukta tutar, bu döngü backoff'la yeniden dener.

Çalıştırma:
    .venv/Scripts/python scripts/pump.py            # sürekli
    .venv/Scripts/python scripts/pump.py --once     # tek tur (cron/test)
"""

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from enricher.ledger import SignalLedger  # noqa: E402
from enricher.outbox import Outbox  # noqa: E402
from enricher.pipeline import SignalPipeline  # noqa: E402
from enricher.policy import load_lifecycle  # noqa: E402
from enricher.telegram import ConsoleSender, TelegramSender  # noqa: E402

logger = logging.getLogger("pump")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    lifecycle = load_lifecycle()
    ob_cfg = lifecycle["outbox"]
    db_dir = Path(os.environ.get("RADAR_SIGNAL_DB_DIR", REPO / "var"))

    telegram = TelegramSender()
    sender = telegram if telegram.configured else ConsoleSender()
    if not telegram.configured:
        logger.warning(
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID yok — bildirimler konsola yazılıyor. "
            "Kurulum: docs/TELEGRAM-KURULUM.md"
        )

    with (
        SignalLedger(db_dir / "signals.sqlite") as led,
        Outbox(
            db_dir / "outbox.sqlite",
            max_attempts=int(ob_cfg["max_attempts"]),
            backoff_seconds=list(ob_cfg["retry_backoff_seconds"]),
            late_delivery_after_minutes=int(ob_cfg["late_delivery_after_minutes"]),
        ) as ob,
    ):
        pipe = SignalPipeline(ledger=led, outbox=ob, lifecycle=lifecycle)
        while True:
            stats = pipe.deliver(sender, now=datetime.now(UTC))
            if any(stats.values()):
                logger.info("pompa: %s", stats)
            if args.once:
                return
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
