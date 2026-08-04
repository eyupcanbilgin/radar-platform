"""Binance -> PIT -> fragility-scored (but direction-free) context production.

What this module does NOT do is as important as what it does.  It measures fragility from
settled funding and hourly open-interest history, and it publishes a context that still
refuses directional use, because no directional rule has passed the research gate.  A
context with a real fragility number and ``direction: null`` is an honest artifact; a
context with an invented neutral direction would not be.

Three states are possible and each one is explicit:
- no rules configured  -> unscored context, ``scoring_rules_unavailable``
- rules configured but history insufficient -> ``feature_unavailable:<feature>:<reason>``
- rules configured and history sufficient -> fragility scored, ``direction_rules_unavailable``
"""

from dataclasses import dataclass
from datetime import datetime

from btc_radar.core.components import evaluate_fragility
from btc_radar.core.config import load_signal_rules, load_weights, weights_hash
from btc_radar.core.context_publisher import ExactHourContextPublisher, PublishResult
from btc_radar.core.snapshot import SnapshotStore, compute_snapshot
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import SignalRulesConfig, WeightsConfig
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
    blockers: tuple[str, ...]


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
        metrics=tuple(sorted({observation.metric for observation in observations})),
    )


def merge_digest_rows(*row_groups: list[dict]) -> list[dict]:
    """Deterministically merge every PIT row that took part in the snapshot.

    The digest must cover the feature history too, not only the ``as_of`` rows.  Otherwise
    two different histories could produce the same ``snapshot_id`` with different fragility
    numbers, and the immutability check would fire on an identity that was never really
    unique.  Ordering is fixed because ``input_digest`` hashes the list in order.
    """
    merged: dict[object, dict] = {}
    for group in row_groups:
        for row in group:
            key = row.get("id", (row["metric"], row["event_time"], row["available_at"]))
            merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            row["metric"],
            row["asset"],
            row["venue"],
            row["event_time"],
            row["available_at"],
            row.get("id", 0),
        ),
    )


def produce_context(
    *,
    as_of_utc: datetime,
    pit_store: PointInTimeStore,
    snapshot_store: SnapshotStore,
    publisher: ExactHourContextPublisher,
    computed_at_utc: datetime | None = None,
    rules: SignalRulesConfig | None = None,
    weights: WeightsConfig | None = None,
    weights_digest: str | None = None,
) -> ContextProductionResult:
    """Publish the immutable exact-hour context for ``as_of_utc``."""
    rules = load_signal_rules() if rules is None else rules
    weights = load_weights() if weights is None else weights
    digest = weights_hash() if weights_digest is None else weights_digest

    current_rows = pit_store.read_as_of(as_of_utc, asset="BTC")
    if rules.rules:
        evaluation = evaluate_fragility(
            store=pit_store, as_of=as_of_utc, rules=rules, weights=weights
        )
        components = evaluation.components
        blockers = frozenset(evaluation.blockers)
        stale_sources = evaluation.stale_sources
        evidence = evaluation.evidence
        rows = merge_digest_rows(current_rows, evaluation.rows_used)
    else:
        # Boş kural kümesi geçici bir durumdur, nötr bir piyasa skoru değildir.
        components = []
        blockers = frozenset({UNSCORED_BLOCKER})
        stale_sources = []
        evidence = []
        rows = current_rows

    snapshot = compute_snapshot(
        rows,
        as_of=as_of_utc,
        weights=weights,
        weights_hash=digest,
        component_builder=lambda _rows, _as_of: components,
        stale_sources=stale_sources,
        computed_at=computed_at_utc,
        evidence=evidence,
    )
    snapshot_created = snapshot_store.put(snapshot)
    publication = publisher.publish(
        snapshot,
        expected_as_of_utc=as_of_utc,
        required_layers=frozenset({"derivatives"}),
        additional_blockers=blockers,
    )
    return ContextProductionResult(
        snapshot=snapshot,
        rows_considered=len(rows),
        snapshot_created=snapshot_created,
        publication=publication,
        blockers=tuple(sorted(blockers)),
    )
