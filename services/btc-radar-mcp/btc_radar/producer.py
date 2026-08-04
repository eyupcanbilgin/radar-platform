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
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from btc_radar.core.backfill import backfill_funding, backfill_open_interest
from btc_radar.core.config import load_signal_rules
from btc_radar.core.context_producer import collect_derivatives, produce_context
from btc_radar.core.context_publisher import ExactHourContextPublisher, require_utc_hour
from btc_radar.core.snapshot import SnapshotStore
from btc_radar.core.store import PointInTimeStore
from btc_radar.providers.binance_futures import BinanceFuturesProvider
from btc_radar.providers.binance_futures_history import (
    FUNDING_SETTLED_METRIC,
    OPEN_INTEREST_HISTORY_RETENTION_DAYS,
    OPEN_INTEREST_HOURLY_METRIC,
    BinanceFuturesHistoryProvider,
)

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
        description="Binance public türev verisini PIT'e al ve fail-closed context yayınla.",
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
        "backfill", help="settled funding ve saatlik OI geçmişini sayfalayarak PIT'e al"
    )
    add_pit_db(backfill)
    backfill.add_argument("--funding-days", type=_positive_days, default=120.0)
    backfill.add_argument(
        "--open-interest-days",
        type=_positive_days,
        default=float(OPEN_INTEREST_HISTORY_RETENTION_DAYS),
        help=f"Binance ~{OPEN_INTEREST_HISTORY_RETENTION_DAYS} günden eskisini saklamaz",
    )

    publish = subparsers.add_parser(
        "publish", help="tam bir UTC saat için değişmez decision-context/v1 yayınla"
    )
    publish.add_argument("--as-of", type=_parse_as_of, required=True)
    add_pit_db(publish)
    publish.add_argument(
        "--snapshot-db",
        type=Path,
        default=_path_env("BTC_RADAR_SNAPSHOT_DB_PATH", SERVICE_ROOT / "var/snapshots.sqlite"),
    )
    publish.add_argument(
        "--context-root",
        type=Path,
        default=_path_env("BTC_RADAR_CONTEXT_ROOT"),
        help="signal servisinin decision-context inbox kökü (veya BTC_RADAR_CONTEXT_ROOT)",
    )
    return parser


def _history_provider(lag_seconds: float) -> BinanceFuturesHistoryProvider:
    return BinanceFuturesHistoryProvider(publication_lag_seconds=lag_seconds)


async def _collect(pit_path: Path, *, history_limit: int) -> dict:
    lag = load_signal_rules().publication_lag_seconds
    with PointInTimeStore(pit_path) as store:
        async with BinanceFuturesProvider() as provider:
            result = await collect_derivatives(provider, store)

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
            "history": history,
            "pit_db": str(pit_path),
            "rows_total": store.count(),
        }


async def _backfill(pit_path: Path, *, funding_days: float, open_interest_days: float) -> dict:
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
    return {
        "command": "backfill",
        "requested_funding_days": funding_days,
        "requested_open_interest_days": open_interest_days,
        "results": [funding.as_payload(), open_interest.as_payload()],
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


def main(argv: Sequence[str] | None = None) -> None:
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
            )
        )
    else:
        if args.context_root is None:
            parser.error("publish için --context-root veya BTC_RADAR_CONTEXT_ROOT zorunlu")
        payload = _publish(
            as_of=args.as_of,
            pit_path=args.pit_db,
            snapshot_path=args.snapshot_db,
            context_root=args.context_root,
        )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
