"""Muhafazakâr mum-içi çözümleme — CR-002 P0-5.

Problem: 1 dakikalık bir mumun içinde hem stop hem hedef seviyesi görülmüşse, OHLC
verisi hangisinin ÖNCE geldiğini söylemez (tick verisi olmadan bilinemez). İki
seçenekten birini seçmek zorundayız ve seçim sonucun iyimserliğini belirler.

KARAR: **stop önce çalışmış sayılır.** Gerekçe: yanlış tarafta yanılmanın bedeli
asimetriktir — hedefi önce saymak backtest'i sistematik olarak güzelleştirir ve
gerçekte yaşanmayacak kârları rapora yazar. Muhafazakâr taraf, kararı gerçek
hayatta hayal kırıklığına değil sürprize açık bırakır.

Aynı kural freqtrade'in `--timeframe-detail 1m` koşusuyla birlikte kullanılır;
burası o kuralın bizim tarafımızdaki tanımı ve testidir.
"""

from dataclasses import dataclass
from typing import Literal

Outcome = Literal["STOP", "TARGET", "NONE"]


@dataclass(frozen=True)
class Candle:
    """Tek bir 1m mum. Zaman bilgisi burada gereksiz: karar yalnız seviyelere bakar."""

    high: float
    low: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"geçersiz mum: high {self.high} < low {self.low}")


def resolve_intracandle(
    candle: Candle, *, stop: float, target: float, is_short: bool = False
) -> Outcome:
    """Mum içinde hangi seviyenin gerçekleştiğini muhafazakâr kuralla çözer.

    İkisi de görülmüşse STOP döner (belirsizlik aleyhimize çözülür).
    """
    if is_short:
        if stop <= target:
            raise ValueError(f"short kurulumda stop ({stop}) hedefin ({target}) ÜSTÜNDE olmalı")
        stop_hit = candle.high >= stop
        target_hit = candle.low <= target
    else:
        if stop >= target:
            raise ValueError(f"long kurulumda stop ({stop}) hedefin ({target}) ALTINDA olmalı")
        stop_hit = candle.low <= stop
        target_hit = candle.high >= target

    if stop_hit:  # belirsizlikte stop kazanır — hedef de görülmüş olsa bile
        return "STOP"
    if target_hit:
        return "TARGET"
    return "NONE"


def is_ambiguous(candle: Candle, *, stop: float, target: float, is_short: bool = False) -> bool:
    """Aynı mumda iki seviye de görüldü mü? (Drift raporunun saydığı durum.)"""
    if is_short:
        return candle.high >= stop and candle.low <= target
    return candle.low <= stop and candle.high >= target


def slippage_bps(fragility: float | None, costs: dict, *, scenario: str) -> float:
    """Rejime bağlı tek yön kayma (bps).

    Kırılganlık eşiği aşıldıysa seçilen senaryo yerine stres senaryosunun bps'i
    uygulanır; eşik ve stres senaryosu adı config'den gelir. Kırılganlık bilinmiyorsa
    (rejim çevrimdışı) senaryonun kendi değeri kullanılır — burada muhafazakârlık
    uydurma bir ceza eklemek değil, bilinmeyeni bilinmiyor saymaktır.
    """
    from costslib import SCENARIO_KEYS

    if scenario not in SCENARIO_KEYS:
        raise ValueError(f"tanımsız senaryo: {scenario!r}")
    dyn = costs.get("dynamic_slippage")
    base = float(costs["stress_scenarios"][SCENARIO_KEYS[scenario]])
    if not dyn or fragility is None:
        return base
    threshold = float(dyn["fragility_threshold"])
    if fragility < threshold:
        return base
    stressed = dyn["stressed_scenario"]
    if stressed not in SCENARIO_KEYS:
        raise ValueError(f"dynamic_slippage.stressed_scenario tanımsız: {stressed!r}")
    stressed_bps = float(costs["stress_scenarios"][SCENARIO_KEYS[stressed]])
    return max(base, stressed_bps)  # stres asla mevcut senaryodan hafif olamaz
