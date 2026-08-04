"""First truthful Binance -> PIT -> UNSCORED context production slice.

This module deliberately does not invent metric-to-score rules. Until a real,
versioned component builder exists, collected observations are preserved in the PIT
input digest while the resulting decision context remains fail-closed.
"""

from dataclasses import dataclass
from datetime import datetime

from btc_radar.core.config import load_signal_rules, load_weights, weights_hash
from btc_radar.core.context_publisher import ExactHourContextPublisher, PublishResult
from btc_radar.core.snapshot import SnapshotStore, compute_snapshot
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.snapshot import RegimeSnapshot
from btc_radar.providers.base import BaseProvider

UNSCORED_BLOCKER = "scoring_rules_unavailable"


@dataclass(frozen=True)
class CollectionResult:
    provider: str
    fetched: int
    inserted: int
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class ContextProductionResult:
    snapshot: RegimeSnapshot
    rows_considered: int
    snapshot_created: bool
    publication: PublishResult


async def collect_derivatives(
    provider: BaseProvider,
    store: PointInTimeStore,
    *,
    metric: str = "all",
) -> CollectionResult:
    """Fetch a complete provider result before starting the atomic PIT append."""
    observations = await provider.fetch(metric, symbol="BTCUSDT")
    inserted = store.append(observations, provider=provider.name)
    return CollectionResult(
        provider=provider.name,
        fetched=len(observations),
        inserted=inserted,
        metrics=tuple(sorted(observation.metric for observation in observations)),
    )


def produce_unscored_context(
    *,
    as_of_utc: datetime,
    pit_store: PointInTimeStore,
    snapshot_store: SnapshotStore,
    publisher: ExactHourContextPublisher,
    computed_at_utc: datetime | None = None,
) -> ContextProductionResult:
    """Publish a valid but unavailable exact-hour context from PIT-known rows.

    The empty builder is an explicit transitional state, not a neutral market score.
    If someone adds rules to config before implementing their component builder, this
    producer fails loudly instead of silently ignoring those rules.
    """
    rules = load_signal_rules()
    if rules.rules:
        raise RuntimeError(
            "signal_rules.yaml artık boş değil; gerçek component builder bağlanmadan "
            "unscored producer çalıştırılamaz"
        )

    rows = pit_store.read_as_of(as_of_utc, asset="BTC")
    snapshot = compute_snapshot(
        rows,
        as_of=as_of_utc,
        weights=load_weights(),
        weights_hash=weights_hash(),
        component_builder=lambda _rows, _as_of: [],
        computed_at=computed_at_utc,
    )
    snapshot_created = snapshot_store.put(snapshot)
    publication = publisher.publish(
        snapshot,
        expected_as_of_utc=as_of_utc,
        required_layers=frozenset({"derivatives"}),
        additional_blockers=frozenset({UNSCORED_BLOCKER}),
    )
    return ContextProductionResult(
        snapshot=snapshot,
        rows_considered=len(rows),
        snapshot_created=snapshot_created,
        publication=publication,
    )
