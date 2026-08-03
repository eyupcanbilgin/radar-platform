"""Deterministik skor toplama motoru — SPEC §5.1 formülleri.

    Yön         = 50 × Σ(wᵢ·dᵢ·qᵢ·fᵢ·uᵢ) / Σ(wᵢ·qᵢ·fᵢ·uᵢ)      → [−100, +100]
    Kırılganlık = 50 × Σ(vᵢ·rᵢ·qᵢ·fᵢ)     / Σ(vᵢ·qᵢ·fᵢ)          → [0, 100]
    Güven       = 100 × ağırlıklı kapsam×kalite oranı              → [0, 100]

KAPSAM SINIRI (bilinçli): metrik→d/r dönüşümü (signal_rules.yaml) ve §6 rejim
sınıflandırma tablosu bu modülde YOKTUR — Faz 1 işidir. Burada yalnız toplama
aritmetiği vardır ve bileşenler (d, r, q, f, u) dışarıdan verilir. Rejim etiketi
şimdilik iki değer alır: güven eşiğin altındaysa "veri_yetersiz", değilse
"siniflandirilmadi_faz1". CR-002 P1-1 (shrinkage, iki kademeli toplama, histerezis)
bu modülü revize edecektir; o iş ayrı kabul kriterleriyle gelir.

Determinizm: bileşenler katman/metrik adına göre sıralanarak toplanır (float
toplama sırası sonucu etkiler); çıktı 6 basamağa yuvarlanır — replay bit-bit eşitliği
bu iki kural üzerine kuruludur.
"""

from dataclasses import dataclass, field

from btc_radar.models.config import WeightsConfig

ROUND_NDIGITS = 6


@dataclass(frozen=True)
class ScoreComponent:
    """Tek metriğin skor katkısı. d/r Faz 1'de signal_rules.yaml'dan üretilecek."""

    layer: str
    metric: str
    d: float  # yön katkısı, [−2, +2]
    r: float  # kırılganlık katkısı, {0, 1, 2}
    q: float  # kalite [0,1]
    f: float  # tazelik [0,1]
    u: float  # bağımsızlık [0,1] (çift sayım grupları, metodoloji §5.5)

    def __post_init__(self) -> None:
        if not -2.0 <= self.d <= 2.0:
            raise ValueError(f"{self.metric}: d aralık dışı ({self.d}); [−2,+2] bekleniyor")
        if not 0.0 <= self.r <= 2.0:
            raise ValueError(f"{self.metric}: r aralık dışı ({self.r}); [0,2] bekleniyor")
        for name in ("q", "f", "u"):
            val = getattr(self, name)
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{self.metric}: {name} aralık dışı ({val}); [0,1] bekleniyor")


@dataclass(frozen=True)
class Scores:
    direction: float | None
    fragility: float | None
    confidence: float
    regime_label: str
    breakdown: list[dict] = field(default_factory=list)
    covered_layers: list[str] = field(default_factory=list)
    missing_layers: list[str] = field(default_factory=list)


def aggregate(components: list[ScoreComponent], weights: WeightsConfig) -> Scores:
    """Bileşenleri SPEC §5.1'e göre üç skora indirger. Saf fonksiyon: I/O yok, saat yok."""
    layers = weights.layers
    fragility_layers = weights.fragility_layers or layers

    unknown = sorted({c.layer for c in components} - set(layers))
    if unknown:
        raise ValueError(f"weights.yaml'da tanımsız katman(lar): {unknown}")

    ordered = sorted(components, key=lambda c: (c.layer, c.metric))

    dir_num = dir_den = 0.0
    frag_num = frag_den = 0.0
    breakdown: list[dict] = []
    per_layer_quality: dict[str, list[float]] = {}

    for c in ordered:
        w = layers[c.layer]
        v = fragility_layers.get(c.layer, w)
        dir_weight = w * c.q * c.f * c.u
        frag_weight = v * c.q * c.f
        dir_num += dir_weight * c.d
        dir_den += dir_weight
        frag_num += frag_weight * c.r
        frag_den += frag_weight
        per_layer_quality.setdefault(c.layer, []).append(c.q * c.f * c.u)
        breakdown.append(
            {
                "layer": c.layer,
                "metric": c.metric,
                "d": c.d,
                "r": c.r,
                "q": c.q,
                "f": c.f,
                "u": c.u,
                "direction_contribution": round(dir_weight * c.d, ROUND_NDIGITS),
                "fragility_contribution": round(frag_weight * c.r, ROUND_NDIGITS),
            }
        )

    direction = round(50.0 * dir_num / dir_den, ROUND_NDIGITS) if dir_den > 0 else None
    fragility = round(50.0 * frag_num / frag_den, ROUND_NDIGITS) if frag_den > 0 else None

    # Güven: her katmanın ağırlığı, o katmanın ortalama q·f·u'suyla ölçeklenir.
    # Veri gelmeyen katman 0 katkı verir → eksik kapsam güveni düşürür (fail-closed).
    total_weight = sum(layers.values())
    covered = 0.0
    for layer_name in sorted(layers):
        quals = per_layer_quality.get(layer_name)
        if quals:
            covered += layers[layer_name] * (sum(sorted(quals)) / len(quals))
    confidence = round(100.0 * covered / total_weight, ROUND_NDIGITS) if total_weight else 0.0

    covered_layers = sorted(per_layer_quality)
    missing_layers = sorted(set(layers) - set(covered_layers))
    threshold = weights.confidence.insufficient_below
    regime_label = "veri_yetersiz" if confidence < threshold else "siniflandirilmadi_faz1"

    return Scores(
        direction=direction,
        fragility=fragility,
        confidence=confidence,
        regime_label=regime_label,
        breakdown=breakdown,
        covered_layers=covered_layers,
        missing_layers=missing_layers,
    )
