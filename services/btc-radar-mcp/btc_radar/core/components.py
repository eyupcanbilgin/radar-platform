"""Turn PIT history into fragility score components through configured rules.

This is the layer SPEC §5.1 calls "metrik → d/r dönüşümü".  Two properties are deliberate:

1. **No direction is produced.**  Every component carries ``d=None``.  Until a directional
   setup has passed the research gate, emitting a direction — even a neutral one — would be
   an invented claim.  Fragility is an observation about crowding and leverage, not a
   forecast (Hedefe Geliştirme Planı, ilke 5).
2. **A missing feature blocks instead of defaulting.**  If a feature cannot be computed
   because history is too short, too gappy or too stale, no component is emitted and a
   blocker is returned.  The context then publishes as ``unavailable``.

Interaction rules (SPEC §5.1) are intentionally NOT implemented in this slice: the
fragility formula has no independence term (u appears only in the direction formula), so an
interaction rule reusing the same two features would double count straight into the score.
That needs the two-stage aggregation from CR-002 P1-1 first.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from btc_radar.core.features import FeatureResult, build_feature
from btc_radar.core.scoring import ScoreComponent
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import FeatureSpec, RuleSpec, SignalRulesConfig, WeightsConfig

FEATURE_BLOCKER_PREFIX = "feature_unavailable"
NO_DIRECTION_BLOCKER = "direction_rules_unavailable"
VENUE = "binance_futures"


@dataclass(frozen=True)
class FragilityEvaluation:
    """Components plus everything a reviewer needs to judge whether they were earned."""

    components: list[ScoreComponent]
    features: list[FeatureResult]
    blockers: list[str]
    stale_sources: list[str]
    rows_used: list[dict]

    @property
    def evidence(self) -> list[dict]:
        return [feature.as_breakdown() for feature in self.features]


def evaluate_fragility(
    *,
    store: PointInTimeStore,
    as_of: datetime,
    rules: SignalRulesConfig,
    weights: WeightsConfig,
    asset: str = "BTC",
) -> FragilityEvaluation:
    """Evaluate every configured rule at ``as_of`` using only PIT-known history."""
    if as_of.tzinfo is None:
        raise ValueError("as_of timezone-aware olmalı")
    as_of = as_of.astimezone(UTC)

    unknown_layers = sorted({rule.layer for rule in rules.rules} - set(weights.layers))
    if unknown_layers:
        raise ValueError(
            f"weights.yaml'da tanımsız katmana atıf yapan kural(lar): {unknown_layers}"
        )

    components: list[ScoreComponent] = []
    features: list[FeatureResult] = []
    blockers: list[str] = []
    stale_sources: list[str] = []
    rows_used: list[dict] = []

    for rule in sorted(rules.rules, key=lambda item: item.id):
        spec = rules.features[rule.feature]
        feature = build_feature(
            rule.feature,
            spec,
            store=store,
            as_of=as_of,
            asset=asset,
            stale_multiple=weights.freshness.stale_multiple,
        )
        features.append(feature)
        rows_used.extend(
            store.read_series(
                metric=spec.metric,
                asset=asset,
                as_of=as_of,
                since=_series_start(as_of, spec),
            )
        )

        if not feature.available:
            blockers.append(f"{FEATURE_BLOCKER_PREFIX}:{rule.feature}:{feature.unavailable_reason}")
            continue

        if feature.freshness_factor < weights.freshness.stale_below_f:
            stale_sources.append(f"{VENUE}:{spec.metric}")

        components.append(
            ScoreComponent(
                layer=rule.layer,
                metric=spec.metric,
                d=None,  # yön iddiası yok — bilinçli
                r=_band_r(rule, feature.percentile),
                q=feature.quality,
                f=feature.freshness_factor,
                # u yalnız yön formülünde kullanılır; yönsel kural olmadığı için hiçbir
                # skoru değiştiremez. Bağımsızlık grupları yön açıldığında anlam kazanır.
                u=1.0,
            )
        )

    if not any(rule.directional for rule in rules.rules):
        blockers.append(NO_DIRECTION_BLOCKER)

    return FragilityEvaluation(
        components=components,
        features=features,
        blockers=sorted(set(blockers)),
        stale_sources=sorted(set(stale_sources)),
        rows_used=rows_used,
    )


def _series_start(as_of: datetime, spec: FeatureSpec) -> datetime:
    """Feature'ın gerçekten okuduğu pencere; digest'e giren satırlar bununla eşleşmeli."""
    return (
        as_of
        - timedelta(days=spec.lookback_days)
        - timedelta(seconds=spec.change_window_seconds or 0.0)
    )


def _band_r(rule: RuleSpec, percentile: float | None) -> float:
    if percentile is None:
        raise ValueError(f"{rule.id}: kullanılabilir feature percentile taşımalı")
    for band in rule.fragility_bands:
        if percentile >= band.min_percentile:
            return band.r
    # Şema 0.0 eşikli yakalayıcı bandı zorunlu kılar; buraya düşmek şema ihlalidir.
    raise ValueError(f"{rule.id}: {percentile} için bant bulunamadı")
