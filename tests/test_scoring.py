"""Skor toplama motoru altın-değer testleri (SPEC §5.1)."""

import pytest

from btc_radar.core.config import load_weights
from btc_radar.core.scoring import ScoreComponent, aggregate


def _c(layer="derivatives", metric="m1", d=0.0, r=0.0, q=1.0, f=1.0, u=1.0):
    return ScoreComponent(layer=layer, metric=metric, d=d, r=r, q=q, f=f, u=u)


@pytest.fixture
def weights():
    return load_weights()


def test_all_layers_max_bullish_gives_plus_100(weights):
    comps = [_c(layer=name, metric=f"m_{name}", d=2.0) for name in weights.layers]
    s = aggregate(comps, weights)
    assert s.direction == 100.0
    assert s.confidence == 100.0
    assert s.missing_layers == []


def test_all_layers_max_bearish_gives_minus_100(weights):
    comps = [_c(layer=name, metric=f"m_{name}", d=-2.0) for name in weights.layers]
    assert aggregate(comps, weights).direction == -100.0


def test_max_fragility_is_100(weights):
    comps = [_c(layer=name, metric=f"m_{name}", r=2.0) for name in weights.layers]
    assert aggregate(comps, weights).fragility == 100.0


def test_golden_two_layer_weighted_average(weights):
    """Elle hesaplanmış altın değer: ağırlıklı ortalamanın 50 katı."""
    comps = [
        _c(layer="derivatives", metric="funding", d=2.0),  # w=0.25
        _c(layer="onchain", metric="sopr", d=-1.0),  # w=0.25
    ]
    # 50 × (0.25·2 + 0.25·(−1)) / (0.25 + 0.25) = 50 × 0.25/0.5 = 25
    assert aggregate(comps, weights).direction == 25.0


def test_quality_reduces_weight_not_direction(weights):
    """Düşük kalite ağırlığı azaltır; tek bileşende yön değişmez, güven düşer."""
    s = aggregate([_c(d=2.0, q=0.5)], weights)
    assert s.direction == 100.0
    assert s.confidence < 100.0


def test_missing_layers_lower_confidence(weights):
    s = aggregate([_c(layer="derivatives", d=1.0)], weights)
    assert s.confidence == pytest.approx(25.0)  # yalnız %25'lik katman kapsandı
    assert s.regime_label == "veri_yetersiz"  # 25 < 55 eşiği
    assert "onchain" in s.missing_layers


def test_confidence_above_threshold_is_not_insufficient(weights):
    comps = [
        _c(layer=name, metric=f"m_{name}", d=0.5)
        for name in ("derivatives", "onchain", "spot_regional", "cycle_sentiment")
    ]  # 0.25+0.25+0.15+0.10 = 0.75 → güven 75
    s = aggregate(comps, weights)
    assert s.confidence == pytest.approx(75.0)
    assert s.regime_label != "veri_yetersiz"


def test_no_components_gives_none_scores_and_zero_confidence(weights):
    s = aggregate([], weights)
    assert s.direction is None and s.fragility is None
    assert s.confidence == 0.0
    assert s.regime_label == "veri_yetersiz"


def test_unknown_layer_fails_loud(weights):
    with pytest.raises(ValueError, match="tanımsız katman"):
        aggregate([_c(layer="uydurma_katman")], weights)


def test_out_of_range_component_fails_loud():
    with pytest.raises(ValueError, match="d aralık dışı"):
        _c(d=3.0)
    with pytest.raises(ValueError, match="q aralık dışı"):
        _c(q=1.5)


def test_breakdown_is_ordered_and_complete(weights):
    comps = [_c(layer="onchain", metric="z"), _c(layer="derivatives", metric="a")]
    s = aggregate(comps, weights)
    assert [(b["layer"], b["metric"]) for b in s.breakdown] == [
        ("derivatives", "a"),
        ("onchain", "z"),
    ]


def test_aggregate_is_pure_and_repeatable(weights):
    comps = [_c(layer=n, metric=f"m_{n}", d=0.7, r=1.0, q=0.9, f=0.8) for n in weights.layers]
    results = {
        (aggregate(comps, weights).direction, aggregate(comps, weights).confidence)
        for _ in range(50)
    }
    assert len(results) == 1
