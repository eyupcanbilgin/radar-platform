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

from decision_engine.context_sets import context_set_sha256, load_context_set  # noqa: E402
from decision_engine.delivery import HourlyDecisionDelivery  # noqa: E402
from decision_engine.forward_trigger import (  # noqa: E402
    ForwardTriggerLedger,
    load_forward_observation_config,
    observe_forward_context,
)
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
from enricher.decision_context import DecisionContextV1  # noqa: E402
from enricher.outbox import Outbox  # noqa: E402
from enricher.policy import load_lifecycle  # noqa: E402
from scripts.fragility_calibration import load_fragility_config  # noqa: E402
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
    parser.add_argument(
        "--f0001-baseline-contexts",
        type=Path,
        help="canlı modda F-0001 forward tetik gözlemini etkinleştiren mühürlü combined set",
    )
    parser.add_argument(
        "--f0001-trigger-ledger",
        type=Path,
        help="varsayılan var/f0001-forward-triggers.sqlite; baseline olmadan kullanılamaz",
    )
    return parser


def _emit(
    result: RuntimeResult,
    *,
    invocation: str,
    forward_observation: dict | None = None,
) -> None:
    payload = {"invocation": invocation, **result.as_dict()}
    if forward_observation is not None:
        payload["f0001_forward_observation"] = forward_observation
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _load_forward_baseline(path: Path) -> tuple[list[dict], dict, dict]:
    observation_config = load_forward_observation_config()
    calibration_config = load_fragility_config()
    if context_set_sha256(path) != observation_config["baseline_context_set_sha256"]:
        raise ValueError("F-0001 forward baseline hash config ile uyuşmuyor")
    contexts = load_context_set(
        path,
        expected_variant=observation_config["baseline_variant"],
        config=calibration_config,
    )
    return contexts, calibration_config, observation_config


def _observe_forward_result(
    *,
    result: RuntimeResult,
    decision_ledger: DecisionLedger,
    trigger_ledger: ForwardTriggerLedger,
    baseline_contexts: list[dict],
    calibration_config: dict,
    observation_config: dict,
) -> dict:
    start = _parse_utc(observation_config["observation_start_utc"])
    if result.as_of_utc < start:
        return {"status": "before_start", "recorded": False, "direction": None}
    row = decision_ledger.get(result.decision.decision_id)
    if row is None or row["context_payload"] is None:
        return {
            "status": "context_unavailable",
            "recorded": False,
            "as_of_utc": result.as_of_utc.isoformat(),
            "direction": None,
        }
    context = DecisionContextV1.model_validate(row["context_payload"])
    return observe_forward_context(
        ledger=trigger_ledger,
        baseline_contexts=baseline_contexts,
        context=context,
        calibration_config=calibration_config,
        observation_config=observation_config,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.daemon and args.as_of is not None:
        parser.error("--as-of yalnız tek-sefer modunda kullanılabilir")
    if args.as_of is not None and args.outbox is not None:
        parser.error("--as-of replay outbox'a yazılamaz; tarihsel bildirim seli engellendi")
    if args.as_of is not None and args.f0001_baseline_contexts is not None:
        parser.error("--as-of replay F-0001 forward defterine bağlanamaz")
    if args.f0001_trigger_ledger is not None and args.f0001_baseline_contexts is None:
        parser.error("--f0001-trigger-ledger için --f0001-baseline-contexts zorunlu")

    try:
        signal_commit = _signal_commit(args.signal_commit)
        ledger_path = _ledger_path(args.ledger, as_of=args.as_of)
        context_root = args.context_dir or _default_context_dir()
        outbox_path = args.outbox or _default_db_dir() / "outbox.sqlite"
        delivery_outbox = Outbox() if args.as_of is not None else _outbox(outbox_path)
        forward = (
            _load_forward_baseline(args.f0001_baseline_contexts)
            if args.f0001_baseline_contexts is not None
            else None
        )
        trigger_path = args.f0001_trigger_ledger or (
            _default_db_dir() / "f0001-forward-triggers.sqlite"
        )
        trigger_ledger = ForwardTriggerLedger(trigger_path) if forward is not None else None
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
                observation = (
                    _observe_forward_result(
                        result=result,
                        decision_ledger=ledger,
                        trigger_ledger=trigger_ledger,
                        baseline_contexts=forward[0],
                        calibration_config=forward[1],
                        observation_config=forward[2],
                    )
                    if forward is not None and trigger_ledger is not None
                    else None
                )
                _emit(result, invocation=invocation, forward_observation=observation)
                if trigger_ledger is not None:
                    trigger_ledger.close()
                return 0

            stop_event = threading.Event()

            def request_stop(_signum, _frame) -> None:
                stop_event.set()

            signal.signal(signal.SIGINT, request_stop)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, request_stop)

            def enqueue_and_emit(result: RuntimeResult) -> None:
                delivery.enqueue_decision(result.decision.decision_id)
                observation = (
                    _observe_forward_result(
                        result=result,
                        decision_ledger=ledger,
                        trigger_ledger=trigger_ledger,
                        baseline_contexts=forward[0],
                        calibration_config=forward[1],
                        observation_config=forward[2],
                    )
                    if forward is not None and trigger_ledger is not None
                    else None
                )
                _emit(
                    result,
                    invocation="utc_daemon",
                    forward_observation=observation,
                )

            scheduler.serve_forever(stop_event=stop_event, on_result=enqueue_and_emit)
            if trigger_ledger is not None:
                trigger_ledger.close()
            return 0
    except Exception as error:
        if "trigger_ledger" in locals() and trigger_ledger is not None:
            trigger_ledger.close()
        payload = {
            "status": "error",
            "error_type": type(error).__name__,
            "error": " ".join(str(error).split())[:500],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
