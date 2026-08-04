"""Rules -> components -> snapshot -> context, using the repository's real config.

The point of running against ``config/signal_rules.yaml`` instead of a test fixture is that
the shipped configuration is what will actually publish contexts.  If its history floors are
unreachable or its bands are incoherent, these tests fail here rather than in production.
"""

from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.components import (
    NO_DIRECTION_BLOCKER,
    evaluate_fragility,
)
from btc_radar.core.config import load_signal_rules, load_weights, weights_hash
from btc_radar.core.context_producer import produce_context
from btc_radar.core.context_publisher import ExactHourContextPublisher
from btc_radar.core.snapshot import SnapshotStore
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.decision_context import DecisionContextV1
from btc_radar.models.observation import RawObservation

AS_OF = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
FUNDING_METRIC = "funding_rate_settled"
OI_NOTIONAL_METRIC = "open_interest_value_1h"
PUBLICATION_LAG = timedelta(seconds=60)


def _observation(*, metric: str, event_at: datetime, value: float, unit: str) -> RawObservation:
    return RawObservation(
        timestamp_utc=event_at,
        retrieved_at_utc=event_at + PUBLICATION_LAG,
        available_at_utc=event_at + PUBLICATION_LAG,
        asset="BTC",
        venue="binance_futures",
        metric=metric,
        raw_value=value,
        unit=unit,
        source_group="derivatives",
        source_url="https://fapi.binance.com/test",
        quality=1.0,
    )


def _funding_history(days: float, *, extreme_latest: bool) -> list[RawObservation]:
    """8h settlements ending before ``AS_OF``; optionally an all-time extreme at the end."""
    count = int(days * 3)
    series = []
    for index in range(count):
        event_at = AS_OF - timedelta(hours=8 * (count - index))
        value = 0.00002 + 0.00001 * (index % 5)
        series.append(
            _observation(metric=FUNDING_METRIC, event_at=event_at, value=value, unit="ratio")
        )
    if extreme_latest and series:
        series[-1] = _observation(
            metric=FUNDING_METRIC,
            event_at=series[-1].timestamp_utc,
            value=0.0031,
            unit="ratio",
        )
    return series


def _open_interest_history(days: float) -> list[RawObservation]:
    """Hourly notional whose 24h change is identically zero — a calm, complete series."""
    count = int(days * 24)
    return [
        _observation(
            metric=OI_NOTIONAL_METRIC,
            event_at=AS_OF - timedelta(hours=count - index),
            value=7_000_000_000.0 + 1_000_000.0 * (index % 24),
            unit="USDT",
        )
        for index in range(count)
    ]


def _seed(store: PointInTimeStore, *, funding_days: float, oi_days: float, extreme: bool) -> None:
    store.append(
        _funding_history(funding_days, extreme_latest=extreme), provider="binance_futures_history"
    )
    store.append(_open_interest_history(oi_days), provider="binance_futures_history")


@pytest.fixture
def rules():
    return load_signal_rules()


@pytest.fixture
def weights():
    return load_weights()


def test_shipped_config_declares_history_floors_and_no_directional_rule(rules):
    assert rules.rules, "kural kümesi boş: fragility üretilemez"
    assert rules.publication_lag_seconds > 0
    for rule in rules.rules:
        assert rule.directional is False
        spec = rules.features[rule.feature]
        assert spec.min_samples >= 2
        assert spec.max_gap_seconds > 0
        assert spec.lookback_days * 86400.0 >= spec.min_span_days * 86400.0


def test_sufficient_history_produces_fragility_but_never_a_direction(rules, weights):
    with PointInTimeStore() as store:
        _seed(store, funding_days=95.0, oi_days=23.0, extreme=True)
        evaluation = evaluate_fragility(store=store, as_of=AS_OF, rules=rules, weights=weights)

    assert [component.metric for component in evaluation.components] == [
        FUNDING_METRIC,
        OI_NOTIONAL_METRIC,
    ]
    assert all(component.d is None for component in evaluation.components)
    # Uç funding tepe bandı (r=2), sakin OI taban bandı (r=0) getirir.
    assert [component.r for component in evaluation.components] == [2.0, 0.0]
    assert evaluation.blockers == [NO_DIRECTION_BLOCKER]
    assert evaluation.stale_sources == []


def test_short_history_blocks_each_feature_with_its_reason(rules, weights):
    with PointInTimeStore() as store:
        _seed(store, funding_days=5.0, oi_days=1.5, extreme=False)
        evaluation = evaluate_fragility(store=store, as_of=AS_OF, rules=rules, weights=weights)

    assert evaluation.components == []
    assert evaluation.blockers == [
        NO_DIRECTION_BLOCKER,
        "feature_unavailable:funding_stress:insufficient_samples",
        "feature_unavailable:oi_buildup:insufficient_samples",
    ]


def test_published_context_carries_fragility_and_still_refuses_direction(tmp_path):
    with PointInTimeStore() as pit, SnapshotStore() as snapshots:
        _seed(pit, funding_days=95.0, oi_days=23.0, extreme=True)
        result = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=ExactHourContextPublisher(tmp_path),
            computed_at_utc=AS_OF + timedelta(minutes=1),
        )

    assert result.snapshot.fragility == 50.0  # r=2 ve r=0 eşit ağırlıkta → 50×(1.0)
    assert result.snapshot.direction is None
    assert result.snapshot.confidence == 25.0  # yalnız derivatives katmanı kapsandı
    assert result.snapshot.regime_label == "veri_yetersiz"
    assert result.snapshot.feature_version == "0.3.0"

    context = DecisionContextV1.model_validate_json(result.publication.path.read_bytes())
    assert context.snapshot.fragility == 50.0
    assert context.snapshot.direction is None
    assert context.data_quality.status == "unavailable"
    assert context.data_quality.directional_decision_allowed is False
    assert NO_DIRECTION_BLOCKER in context.data_quality.blockers
    assert "regime_unavailable" in context.data_quality.blockers
    assert "scoring_rules_unavailable" not in context.data_quality.blockers


def test_snapshot_evidence_records_how_much_history_backed_the_score(tmp_path):
    with PointInTimeStore() as pit, SnapshotStore() as snapshots:
        _seed(pit, funding_days=95.0, oi_days=23.0, extreme=True)
        result = produce_context(
            as_of_utc=AS_OF,
            pit_store=pit,
            snapshot_store=snapshots,
            publisher=ExactHourContextPublisher(tmp_path),
            computed_at_utc=AS_OF + timedelta(minutes=1),
        )

    evidence = {item["feature"]: item for item in result.snapshot.evidence}
    assert set(evidence) == {"funding_stress", "oi_buildup"}
    funding = evidence["funding_stress"]
    assert funding["sample_count"] >= 120
    assert funding["span_seconds"] >= 45 * 86400
    assert funding["max_gap_seconds"] == 28800.0
    assert funding["unavailable_reason"] is None
    assert evidence["oi_buildup"]["sample_count"] >= 336


def test_history_is_bound_to_the_snapshot_id(tmp_path):
    """Değişen geçmiş = değişen kimlik: aksi hâlde aynı id farklı skoru saklardı."""
    identities = []
    for extra in (0.0, 0.00777):
        with PointInTimeStore() as pit, SnapshotStore() as snapshots:
            _seed(pit, funding_days=95.0, oi_days=23.0, extreme=True)
            if extra:
                pit.append(
                    [
                        _observation(
                            metric=FUNDING_METRIC,
                            event_at=AS_OF - timedelta(days=40),
                            value=extra,
                            unit="ratio",
                        )
                    ],
                    provider="binance_futures_history",
                )
            result = produce_context(
                as_of_utc=AS_OF,
                pit_store=pit,
                snapshot_store=snapshots,
                publisher=ExactHourContextPublisher(tmp_path / str(extra)),
                computed_at_utc=AS_OF + timedelta(minutes=1),
            )
            identities.append(result.snapshot.snapshot_id)

    assert identities[0] != identities[1]


def test_replay_of_the_same_history_is_bit_identical(tmp_path):
    def run(directory) -> tuple[str, str, float | None]:
        with PointInTimeStore() as pit, SnapshotStore() as snapshots:
            _seed(pit, funding_days=95.0, oi_days=23.0, extreme=True)
            result = produce_context(
                as_of_utc=AS_OF,
                pit_store=pit,
                snapshot_store=snapshots,
                publisher=ExactHourContextPublisher(directory),
                computed_at_utc=AS_OF + timedelta(minutes=7),
                weights_digest=weights_hash(),
            )
            return (
                result.snapshot.snapshot_id,
                result.snapshot.content_hash,
                result.snapshot.fragility,
            )

    assert run(tmp_path / "first") == run(tmp_path / "second")
