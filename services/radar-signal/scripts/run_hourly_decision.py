"""Run the BTCUSDT 1h paper decision ledger once or as a UTC daemon.

This process fetches public closed candles and reads an exact-hour context artifact. It has
no directional setup source and never sends an exchange order; current healthy output is WAIT.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from decision_engine.delivery import HourlyDecisionDelivery  # noqa: E402
from decision_engine.ledger import DecisionLedger  # noqa: E402
from decision_engine.runtime import (  # noqa: E402
    DEFAULT_GRACE_SECONDS,
    HourlyDecisionRuntime,
    RuntimeResult,
    UtcHourlyScheduler,
)
from decision_engine.sources import (  # noqa: E402
    BinanceUsdMClosedCandleSource,
    JsonDecisionContextSource,
)
from enricher.outbox import Outbox  # noqa: E402
from enricher.policy import load_lifecycle  # noqa: E402
from scripts.provenance import git_commit, git_is_dirty  # noqa: E402


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--as-of timezone-aware olmalı; örn. ...T12:00:00Z")
    return parsed.astimezone(UTC)


def _signal_commit(explicit: str | None) -> str:
    if explicit is not None:
        if not re.fullmatch(r"[a-f0-9]{12}", explicit):
            raise ValueError("--signal-commit tam 12 küçük hex karakter olmalı")
    try:
        dirty = git_is_dirty()
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        if explicit is not None:
            return explicit
        raise RuntimeError(
            "git checkout bulunamadı; paketli ortamda --signal-commit zorunlu"
        ) from error
    if dirty:
        raise RuntimeError(
            "radar-signal çalışma ağacı kirli; karar provenance için önce commit oluşturun"
        )
    current = git_commit()
    if explicit is not None and explicit != current:
        raise RuntimeError(
            f"--signal-commit checkout ile uyuşmuyor: gelen={explicit}, mevcut={current}"
        )
    return current


def _default_db_dir() -> Path:
    configured = os.getenv("RADAR_SIGNAL_DB_DIR")
    return Path(configured) if configured else SERVICE_ROOT / "var"


def _default_context_dir() -> Path:
    configured = os.getenv("RADAR_SIGNAL_CONTEXT_DIR")
    return Path(configured) if configured else SERVICE_ROOT / "var" / "decision-context"


def _ledger_path(explicit: Path | None, *, as_of: datetime | None) -> Path:
    if explicit is not None:
        return explicit
    name = "hourly-replay.sqlite" if as_of is not None else "hourly-decisions.sqlite"
    return _default_db_dir() / name


def _outbox(path: Path) -> Outbox:
    config = load_lifecycle()["outbox"]
    return Outbox(
        path,
        max_attempts=int(config["max_attempts"]),
        backoff_seconds=list(config["retry_backoff_seconds"]),
        late_delivery_after_minutes=int(config["late_delivery_after_minutes"]),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="UTC saat sınırlarını sürekli izle; varsayılan tek-sefer çalışmadır",
    )
    parser.add_argument(
        "--as-of",
        type=_parse_utc,
        help="yalnız tek-sefer replay/backfill saati; canlı paper karar gibi yorumlanmaz",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="normalde hourly-decisions.sqlite; --as-of ile hourly-replay.sqlite",
    )
    parser.add_argument(
        "--outbox",
        type=Path,
        default=None,
        help="canlı çalışmada varsayılan var/outbox.sqlite; replay bildirim üretmez",
    )
    parser.add_argument(
        "--context-dir",
        type=Path,
        default=None,
        help="exact-hour decision-context/v1 inbox kökü",
    )
    parser.add_argument(
        "--grace-seconds",
        type=int,
        default=DEFAULT_GRACE_SECONDS,
        help=f"mum kapanışı sonrası bekleme; varsayılan {DEFAULT_GRACE_SECONDS}",
    )
    parser.add_argument(
        "--signal-commit",
        help="git bulunmayan paketli ortam için açık 12-char signal commit",
    )
    return parser


def _emit(result: RuntimeResult, *, invocation: str) -> None:
    payload = {"invocation": invocation, **result.as_dict()}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.daemon and args.as_of is not None:
        parser.error("--as-of yalnız tek-sefer modunda kullanılabilir")
    if args.as_of is not None and args.outbox is not None:
        parser.error("--as-of replay outbox'a yazılamaz; tarihsel bildirim seli engellendi")

    try:
        signal_commit = _signal_commit(args.signal_commit)
        ledger_path = _ledger_path(args.ledger, as_of=args.as_of)
        context_root = args.context_dir or _default_context_dir()
        outbox_path = args.outbox or _default_db_dir() / "outbox.sqlite"
        delivery_outbox = Outbox() if args.as_of is not None else _outbox(outbox_path)
        with DecisionLedger(ledger_path) as ledger, delivery_outbox as outbox:
            delivery = HourlyDecisionDelivery(ledger=ledger, outbox=outbox)
            candle_source = BinanceUsdMClosedCandleSource(close_grace_seconds=args.grace_seconds)
            runtime = HourlyDecisionRuntime(
                ledger=ledger,
                candle_source=candle_source,
                context_source=JsonDecisionContextSource(context_root),
                signal_commit=signal_commit,
            )
            scheduler = UtcHourlyScheduler(
                runtime,
                grace_seconds=args.grace_seconds,
                clock=candle_source.exchange_time,
            )
            if not args.daemon:
                result = scheduler.run_once(as_of_utc=args.as_of)
                invocation = "explicit_replay" if args.as_of is not None else "latest_due_once"
                if args.as_of is None:
                    delivery.enqueue_decision(result.decision.decision_id)
                _emit(result, invocation=invocation)
                return 0

            stop_event = threading.Event()

            def request_stop(_signum, _frame) -> None:
                stop_event.set()

            signal.signal(signal.SIGINT, request_stop)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, request_stop)

            def enqueue_and_emit(result: RuntimeResult) -> None:
                delivery.enqueue_decision(result.decision.decision_id)
                _emit(result, invocation="utc_daemon")

            scheduler.serve_forever(stop_event=stop_event, on_result=enqueue_and_emit)
            return 0
    except Exception as error:
        payload = {
            "status": "error",
            "error_type": type(error).__name__,
            "error": " ".join(str(error).split())[:500],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
