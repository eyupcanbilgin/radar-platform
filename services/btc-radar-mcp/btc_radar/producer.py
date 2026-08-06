"""Collector, history backfill and exact-hour context producer CLI.

Collection and publication are separate commands on purpose. A sample retrieved after an
hour boundary must not be backdated into that hour; an eventual scheduler should collect
throughout the hour and invoke ``publish`` only after the close grace.

``collect`` also pulls the newest history pages every run.  That is not redundancy: the
hourly open-interest endpoint only retains about 30 days, so any history older than that
can exist solely because we kept storing it ourselves.
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import threading
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path

from btc_radar.core.backfill import backfill_funding, backfill_open_interest, backfill_spot_ohlcv
from btc_radar.core.config import load_f0001_locked_oos, load_signal_rules
from btc_radar.core.context_producer import collect_derivatives, produce_context
from btc_radar.core.context_publisher import ExactHourContextPublisher, require_utc_hour
from btc_radar.core.coverage import collection_coverage
from btc_radar.core.heartbeat import HeartbeatStore
from btc_radar.core.research_contexts import generate_f0001_context_sets
from btc_radar.core.runlock import exclusive_run_lock
from btc_radar.core.scheduler import (
    DEFAULT_COLLECT_INTERVAL_SECONDS,
    DEFAULT_PUBLISH_GRACE_SECONDS,
    TASK_COLLECT,
    TASK_PUBLISH,
    ProducerScheduler,
    latest_due_hour,
)
from btc_radar.core.snapshot import SnapshotStore
from btc_radar.core.store import PointInTimeStore
from btc_radar.providers.binance_futures import BinanceFuturesProvider
from btc_radar.providers.binance_futures_history import (
    FUNDING_SETTLED_METRIC,
    OPEN_INTEREST_HISTORY_RETENTION_DAYS,
    OPEN_INTEREST_HOURLY_METRIC,
    BinanceFuturesHistoryProvider,
)
from btc_radar.providers.binance_spot import BinanceSpotProvider
from btc_radar.providers.binance_spot_history import BinanceSpotHistoryProvider

SERVICE_ROOT = Path(__file__).resolve().parent.parent


def _path_env(name: str, default: Path | None = None) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else default


def _parse_as_of(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("ISO-8601 UTC saat bekleniyor") from error
    try:
        return require_utc_hour(parsed)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _positive_days(value: str) -> float:
    try:
        days = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("gün sayısı sayısal olmalı") from error
    if days <= 0:
        raise argparse.ArgumentTypeError("gün sayısı > 0 olmalı")
    return days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="btc-radar-producer",
        description="Binance public piyasa verisini PIT'e al ve fail-closed context yayınla.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_pit_db(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--pit-db",
            type=Path,
            default=_path_env("BTC_RADAR_DB_PATH", SERVICE_ROOT / "var/pit.sqlite"),
        )

    collect = subparsers.add_parser(
        "collect", help="anlık Binance türev örneğini ve en yeni geçmiş sayfalarını PIT'e yaz"
    )
    add_pit_db(collect)
    collect.add_argument(
        "--history-limit",
        type=int,
        default=3,
        help="her koşuda çekilecek en yeni geçmiş kaydı sayısı (0 = geçmişi atla)",
    )

    backfill = subparsers.add_parser(
        "backfill", help="funding, saatlik OI ve spot OHLCV geçmişini sayfalayarak PIT'e al"
    )
    add_pit_db(backfill)
    backfill.add_argument("--funding-days", type=_positive_days, default=120.0)
    backfill.add_argument(
        "--open-interest-days",
        type=_positive_days,
        default=float(OPEN_INTEREST_HISTORY_RETENTION_DAYS),
        help=f"Binance ~{OPEN_INTEREST_HISTORY_RETENTION_DAYS} günden eskisini saklamaz",
    )
    backfill.add_argument(
        "--spot-days",
        type=_positive_days,
        default=120.0,
        help="kapanmış Binance spot 1h OHLCV geçmişi (basis/depth geçmişi üretmez)",
    )

    def add_snapshot_db(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--snapshot-db",
            type=Path,
            default=_path_env("BTC_RADAR_SNAPSHOT_DB_PATH", SERVICE_ROOT / "var/snapshots.sqlite"),
        )

    def add_context_root(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--context-root",
            type=Path,
            default=_path_env("BTC_RADAR_CONTEXT_ROOT"),
            help="signal servisinin decision-context inbox kökü (veya BTC_RADAR_CONTEXT_ROOT)",
        )

    def add_heartbeat_db(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--heartbeat-db",
            type=Path,
            default=_path_env("BTC_RADAR_HEARTBEAT_DB_PATH", SERVICE_ROOT / "var/heartbeat.sqlite"),
            help="toplama/yayın koşu kütüğü (kesintisiz işletim kanıtı)",
        )

    publish = subparsers.add_parser(
        "publish", help="tam bir UTC saat için değişmez decision-context/v1 yayınla"
    )
    publish.add_argument("--as-of", type=_parse_as_of, required=True)
    add_pit_db(publish)
    add_snapshot_db(publish)
    add_context_root(publish)

    research = subparsers.add_parser(
        "research-contexts", help="F-0001 ana ve ablation tarihsel context setlerini üret"
    )
    research.add_argument("--start", type=_parse_as_of, required=True)
    research.add_argument("--end-exclusive", type=_parse_as_of, required=True)
    research.add_argument("--output-root", type=Path, required=True)
    research.add_argument("--snapshot-root", type=Path, required=True)
    add_pit_db(research)

    run = subparsers.add_parser(
        "run", help="saat içi toplama + kapanan saat yayınını zamanlayıcıyla yürüt"
    )
    add_pit_db(run)
    add_snapshot_db(run)
    add_context_root(run)
    add_heartbeat_db(run)
    run.add_argument(
        "--daemon",
        action="store_true",
        help="sürekli çalış; varsayılan tek geçişlik (cron/Task Scheduler için) tick'tir",
    )
    run.add_argument(
        "--collect-interval-seconds", type=int, default=DEFAULT_COLLECT_INTERVAL_SECONDS
    )
    run.add_argument("--publish-grace-seconds", type=int, default=DEFAULT_PUBLISH_GRACE_SECONDS)
    run.add_argument("--history-limit", type=int, default=3)
    run.add_argument(
        "--catch-up-hours",
        type=int,
        default=0,
        help="kesintiden sonra en fazla kaç kaçırılmış saat yayınlansın (0 = yalnız güncel saat)",
    )
    run.add_argument(
        "--lock-file",
        type=Path,
        default=None,
        help="tek örnek koruması; ikinci daemon aynı kilitle başlatılamaz",
    )

    status = subparsers.add_parser(
        "status", help="koşu kütüğü özeti ve toplanan serinin kapsama raporu"
    )
    add_pit_db(status)
    add_heartbeat_db(status)
    status.add_argument("--window-days", type=_positive_days, default=7.0)
    return parser


def _history_provider(lag_seconds: float) -> BinanceFuturesHistoryProvider:
    return BinanceFuturesHistoryProvider(publication_lag_seconds=lag_seconds)


def _spot_history_provider(lag_seconds: float) -> BinanceSpotHistoryProvider:
    return BinanceSpotHistoryProvider(publication_lag_seconds=lag_seconds)


async def _collect(pit_path: Path, *, history_limit: int) -> dict:
    lag = load_signal_rules().publication_lag_seconds
    with PointInTimeStore(pit_path) as store:
        async with BinanceFuturesProvider() as provider:
            result = await collect_derivatives(provider, store)
            order_book = await collect_derivatives(provider, store, metric="order_book")
            # futures_provider paylaşılır: basis bacağı ayrı bir premiumIndex çağrısı yapmaz.
            async with BinanceSpotProvider(futures_provider=provider) as spot_provider:
                spot_result = await collect_derivatives(spot_provider, store, metric="all")

        history: list[dict] = []
        if history_limit > 0:
            async with _history_provider(lag) as provider:
                for metric in (FUNDING_SETTLED_METRIC, OPEN_INTEREST_HOURLY_METRIC):
                    observations = await provider.fetch(metric, limit=history_limit)
                    history.append(
                        {
                            "metric": metric,
                            "fetched": len(observations),
                            "inserted": store.append(observations, provider=provider.name),
                        }
                    )

        return {
            "command": "collect",
            "provider": result.provider,
            "fetched": result.fetched,
            "inserted": result.inserted,
            "metrics": list(result.metrics),
            "order_book": {
                "provider": order_book.provider,
                "fetched": order_book.fetched,
                "inserted": order_book.inserted,
                "metrics": list(order_book.metrics),
            },
            "spot": {
                "provider": spot_result.provider,
                "fetched": spot_result.fetched,
                "inserted": spot_result.inserted,
                "metrics": list(spot_result.metrics),
            },
            "history": history,
            "pit_db": str(pit_path),
            "rows_total": store.count(),
        }


async def _backfill(
    pit_path: Path,
    *,
    funding_days: float,
    open_interest_days: float,
    spot_days: float,
) -> dict:
    lag = load_signal_rules().publication_lag_seconds
    now = datetime.now(UTC)
    with PointInTimeStore(pit_path) as store:
        async with _history_provider(lag) as provider:
            funding = await backfill_funding(
                provider,
                store,
                start=now - timedelta(days=funding_days),
                end=now,
            )
            open_interest = await backfill_open_interest(
                provider,
                store,
                start=now - timedelta(days=open_interest_days),
                end=now,
            )
        async with _spot_history_provider(lag) as provider:
            spot = await backfill_spot_ohlcv(
                provider,
                store,
                start=now - timedelta(days=spot_days),
                end=now,
            )
    return {
        "command": "backfill",
        "requested_funding_days": funding_days,
        "requested_open_interest_days": open_interest_days,
        "requested_spot_days": spot_days,
        "results": [funding.as_payload(), open_interest.as_payload(), spot.as_payload()],
        "pit_db": str(pit_path),
    }


def _publish(
    *,
    as_of: datetime,
    pit_path: Path,
    snapshot_path: Path,
    context_root: Path,
) -> dict:
    with PointInTimeStore(pit_path) as pit, SnapshotStore(snapshot_path) as snapshots:
        result = produce_context(
            as_of_utc=as_of,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=ExactHourContextPublisher(context_root),
        )
    return {
        "command": "publish",
        "status": result.publication.status,
        "as_of_utc": as_of.astimezone(UTC).isoformat(),
        "snapshot_id": result.snapshot.snapshot_id,
        "rows_considered": result.rows_considered,
        "direction": result.snapshot.direction,
        "fragility": result.snapshot.fragility,
        "confidence": result.snapshot.confidence,
        "regime_label": result.snapshot.regime_label,
        "blockers": list(result.blockers),
        "directional_decision_allowed": False,
        "context_path": str(result.publication.path.resolve()),
    }


def _scheduler(args: argparse.Namespace, heartbeat: HeartbeatStore) -> ProducerScheduler:
    return ProducerScheduler(
        collect=lambda: asyncio.run(_collect(args.pit_db, history_limit=args.history_limit)),
        publish=lambda as_of: _publish(
            as_of=as_of,
            pit_path=args.pit_db,
            snapshot_path=args.snapshot_db,
            context_root=args.context_root,
        ),
        heartbeat=heartbeat,
        collect_interval_seconds=args.collect_interval_seconds,
        publish_grace_seconds=args.publish_grace_seconds,
        catch_up_hours=args.catch_up_hours,
    )


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False), flush=True)


def _run(args: argparse.Namespace) -> None:
    """One deterministic tick, or the same tick repeated until a stop signal."""
    with ExitStack() as stack:
        if args.lock_file is not None:
            stack.enter_context(exclusive_run_lock(args.lock_file))
        heartbeat = stack.enter_context(HeartbeatStore(args.heartbeat_db))
        scheduler = _scheduler(args, heartbeat)

        if not args.daemon:
            for run in scheduler.tick():
                _emit({"invocation": "single_tick", **run.as_payload()})
            return

        stop_event = threading.Event()

        def request_stop(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, request_stop)

        _emit(
            {
                "invocation": "daemon_start",
                "collect_interval_seconds": scheduler.collect_interval_seconds,
                "publish_grace_seconds": scheduler.publish_grace_seconds,
                "catch_up_hours": scheduler.catch_up_hours,
                "heartbeat_db": str(args.heartbeat_db),
            }
        )
        scheduler.serve_forever(
            stop_event=stop_event,
            on_run=lambda run: _emit({"invocation": "daemon", **run.as_payload()}),
        )
        _emit({"invocation": "daemon_stop"})


def _status(args: argparse.Namespace) -> dict:
    now = datetime.now(UTC)
    rules = load_signal_rules()
    window_seconds = args.window_days * 86400.0
    with (
        HeartbeatStore(args.heartbeat_db) as heartbeat,
        PointInTimeStore(args.pit_db) as pit,
    ):
        published = heartbeat.latest_success_as_of(TASK_PUBLISH)
        due = latest_due_hour(now, grace_seconds=DEFAULT_PUBLISH_GRACE_SECONDS)
        coverage = collection_coverage(pit, rules=rules, as_of=now, window_seconds=window_seconds)
        return {
            "command": "status",
            "now_utc": now.isoformat(),
            "window_days": args.window_days,
            "tasks": heartbeat.summary(now=now, tasks=(TASK_COLLECT, TASK_PUBLISH)),
            "publish": {
                "latest_published_as_of": None if published is None else published.isoformat(),
                "latest_due_as_of": due.isoformat(),
                "hours_behind": (
                    None if published is None else int((due - published).total_seconds() // 3600)
                ),
            },
            "coverage": [item.as_payload() for item in coverage],
            "healthy": all(item.healthy for item in coverage) and coverage != [],
        }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI girişi. Operasyonel hata ham traceback değil, makine-okunur bir kayıt olmalı."""
    try:
        return _dispatch(argv)
    except SystemExit:
        raise
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(error).__name__,
                    "error": " ".join(str(error).split())[:500],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2


def _dispatch(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        if args.history_limit < 0:
            parser.error("--history-limit negatif olamaz")
        payload = asyncio.run(_collect(args.pit_db, history_limit=args.history_limit))
    elif args.command == "backfill":
        payload = asyncio.run(
            _backfill(
                args.pit_db,
                funding_days=args.funding_days,
                open_interest_days=args.open_interest_days,
                spot_days=args.spot_days,
            )
        )
    elif args.command == "status":
        payload = _status(args)
    elif args.command == "research-contexts":
        with PointInTimeStore(args.pit_db) as pit:
            payload = generate_f0001_context_sets(
                start_utc=args.start,
                end_exclusive_utc=args.end_exclusive,
                locked_oos_start_utc=load_f0001_locked_oos(),
                pit_store=pit,
                snapshot_root=args.snapshot_root,
                output_root=args.output_root,
                rules=load_signal_rules(),
            )
    elif args.command == "run":
        if args.context_root is None:
            parser.error("run için --context-root veya BTC_RADAR_CONTEXT_ROOT zorunlu")
        if args.history_limit < 0:
            parser.error("--history-limit negatif olamaz")
        for check, message in (
            (args.collect_interval_seconds <= 0, "--collect-interval-seconds > 0 olmalı"),
            (
                not 0 <= args.publish_grace_seconds < 3600,
                "--publish-grace-seconds 0..3599 aralığında olmalı",
            ),
            (args.catch_up_hours < 0, "--catch-up-hours negatif olamaz"),
        ):
            if check:
                parser.error(message)
        _run(args)
        return 0
    else:
        if args.context_root is None:
            parser.error("publish için --context-root veya BTC_RADAR_CONTEXT_ROOT zorunlu")
        payload = _publish(
            as_of=args.as_of,
            pit_path=args.pit_db,
            snapshot_path=args.snapshot_db,
            context_root=args.context_root,
        )
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
