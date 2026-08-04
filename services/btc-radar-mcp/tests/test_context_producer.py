from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.context_producer import collect_derivatives, produce_context
from btc_radar.core.context_publisher import ExactHourContextPublisher
from btc_radar.core.snapshot import SnapshotStore, input_digest
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import SignalRulesConfig
from btc_radar.models.decision_context import DecisionContextV1
from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider

AS_OF = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
# Kural kümesi boşken producer skorsuz yolda kalır; bu testler o yolu doğrular.
EMPTY_RULES = SignalRulesConfig(version="test-empty")


def _observations(*, retrieved_at: datetime) -> list[RawObservation]:
    values = {
        "mark_price": (65_000.0, "USDT/BTC"),
        "funding_rate": (0.0001, "ratio"),
        "open_interest": (95_000.0, "BTC"),
    }
    return [
        RawObservation(
            timestamp_utc=retrieved_at - timedelta(seconds=1),
            retrieved_at_utc=retrieved_at,
            available_at_utc=retrieved_at,
            asset="BTC",
            venue="binance_futures",
            metric=metric,
            raw_value=value,
            unit=unit,
            source_group="derivatives",
            source_url="https://fapi.binance.com/test",
            quality=1.0,
        )
        for metric, (value, unit) in values.items()
    ]


class FakeProvider(BaseProvider):
    name = "fake_binance"
    source_group = "derivatives"

    def __init__(self, observations=None, error: Exception | None = None):
        self.observations = observations or []
        self.error = error

    async def fetch(self, metric: str, **params):
        assert metric == "all"
        assert params == {"symbol": "BTCUSDT"}
        if self.error:
            raise self.error
        return self.observations


async def test_collect_appends_complete_normalized_bundle():
    with PointInTimeStore() as store:
        result = await collect_derivatives(
            FakeProvider(_observations(retrieved_at=AS_OF - timedelta(minutes=1))), store
        )
        assert result.fetched == result.inserted == 3
        assert result.metrics == ("funding_rate", "mark_price", "open_interest")
        assert store.count() == 3


async def test_fetch_failure_cannot_partially_append():
    with PointInTimeStore() as store:
        with pytest.raises(RuntimeError, match="network down"):
            await collect_derivatives(FakeProvider(error=RuntimeError("network down")), store)
        assert store.count() == 0


def test_post_as_of_collection_is_excluded_and_context_fails_closed(tmp_path):
    with (
        PointInTimeStore() as pit,
        SnapshotStore() as snapshots,
    ):
        pit.append(
            _observations(retrieved_at=AS_OF + timedelta(seconds=30)),
            provider="fake_binance",
        )
        result = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=ExactHourContextPublisher(tmp_path),
            rules=EMPTY_RULES,
            computed_at_utc=AS_OF + timedelta(minutes=1),
        )

        assert result.rows_considered == 0
        assert result.snapshot.input_digest == input_digest([])
        assert result.snapshot.direction is None
        assert result.snapshot.fragility is None
        assert result.snapshot.confidence == 0
        assert result.snapshot.regime_label == "veri_yetersiz"
        context = DecisionContextV1.model_validate_json(result.publication.path.read_bytes())
        assert context.data_quality.directional_decision_allowed is False
        assert "scoring_rules_unavailable" in context.data_quality.blockers


def test_pre_as_of_rows_enter_digest_but_never_become_fake_scores(tmp_path):
    with (
        PointInTimeStore() as pit,
        SnapshotStore() as snapshots,
    ):
        pit.append(
            _observations(retrieved_at=AS_OF - timedelta(minutes=1)),
            provider="fake_binance",
        )
        result = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=ExactHourContextPublisher(tmp_path),
            rules=EMPTY_RULES,
            computed_at_utc=AS_OF + timedelta(minutes=1),
        )

        assert result.rows_considered == 3
        assert result.snapshot.input_digest != input_digest([])
        assert result.snapshot.direction is None
        assert result.snapshot.breakdown == []


def test_replay_is_semantically_idempotent(tmp_path):
    with PointInTimeStore() as pit, SnapshotStore() as snapshots:
        pit.append(
            _observations(retrieved_at=AS_OF - timedelta(minutes=1)),
            provider="fake_binance",
        )
        publisher = ExactHourContextPublisher(tmp_path)
        first = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=publisher,
            rules=EMPTY_RULES,
            computed_at_utc=AS_OF + timedelta(minutes=1),
        )
        second = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=publisher,
            rules=EMPTY_RULES,
            computed_at_utc=AS_OF + timedelta(minutes=2),
        )

        assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
        assert first.snapshot.content_hash == second.snapshot.content_hash
        assert first.snapshot_created is True
        assert second.snapshot_created is False
        assert second.publication.status == "idempotent"
