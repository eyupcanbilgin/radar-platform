"""One-shot collector and exact-hour context producer CLI.

Collection and publication are separate commands on purpose. A sample retrieved after an
hour boundary must not be backdated into that hour; an eventual scheduler should collect
throughout the hour and invoke ``publish`` only after the close grace.
"""

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from btc_radar.core.context_producer import collect_derivatives, produce_unscored_context
from btc_radar.core.context_publisher import ExactHourContextPublisher, require_utc_hour
from btc_radar.core.snapshot import SnapshotStore
from btc_radar.core.store import PointInTimeStore
from btc_radar.providers.binance_futures import BinanceFuturesProvider

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="btc-radar-producer",
        description="Binance public türev verisini PIT'e al ve fail-closed context yayınla.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="anlık Binance türev örneğini PIT'e yaz")
    collect.add_argument(
        "--pit-db",
        type=Path,
        default=_path_env("BTC_RADAR_DB_PATH", SERVICE_ROOT / "var/pit.sqlite"),
    )

    publish = subparsers.add_parser(
        "publish", help="tam bir UTC saat için değişmez decision-context/v1 yayınla"
    )
    publish.add_argument("--as-of", type=_parse_as_of, required=True)
    publish.add_argument(
        "--pit-db",
        type=Path,
        default=_path_env("BTC_RADAR_DB_PATH", SERVICE_ROOT / "var/pit.sqlite"),
    )
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


async def _collect(pit_path: Path) -> dict:
    with PointInTimeStore(pit_path) as store:
        async with BinanceFuturesProvider() as provider:
            result = await collect_derivatives(provider, store)
        return {
            "command": "collect",
            "provider": result.provider,
            "fetched": result.fetched,
            "inserted": result.inserted,
            "metrics": list(result.metrics),
            "pit_db": str(pit_path),
            "rows_total": store.count(),
        }


def _publish(
    *,
    as_of: datetime,
    pit_path: Path,
    snapshot_path: Path,
    context_root: Path,
) -> dict:
    with PointInTimeStore(pit_path) as pit, SnapshotStore(snapshot_path) as snapshots:
        result = produce_unscored_context(
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
        "directional_decision_allowed": False,
        "context_path": str(result.publication.path.resolve()),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        payload = asyncio.run(_collect(args.pit_db))
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
