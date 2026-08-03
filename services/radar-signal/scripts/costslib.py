"""config/costs.yaml yükleme ve senaryo çözümleme (CR-5).

Fail-loud: dosya yoksa, senaryo tanımsızsa veya değerler aralık dışıysa hata fırlatır;
sessiz varsayılana düşülmez. bt.py ve testler bu modülü kullanır.
"""

import hashlib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
COSTS_PATH = REPO / "config" / "costs.yaml"

SCENARIO_KEYS = {
    "optimistic_maker": "optimistic_maker_bps",
    "realistic": "realistic_bps",
    "taker_heavy": "taker_heavy_bps",
    "stressed": "stressed_bps",
    "cascade": "cascade_bps",
}


def load_costs(path: Path | None = None) -> dict:
    p = path or COSTS_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p.name} boş ya da dict değil")
    for key in ("version", "fees", "slippage_oneway", "funding", "stress_scenarios"):
        if key not in raw:
            raise ValueError(f"costs.yaml eksik alan: {key}")
    for fee_name in ("taker", "maker"):
        fee = raw["fees"].get(fee_name)
        if not isinstance(fee, int | float) or not 0 < fee < 0.01:
            raise ValueError(f"fees.{fee_name} mantıksız: {fee!r} (0 < x < 0.01 bekleniyor)")
    return raw


def costs_hash(path: Path | None = None) -> str:
    p = path or COSTS_PATH
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def effective_fee(costs: dict, scenario: str) -> float:
    """Tek yön efektif maliyet oranı: taker komisyon + senaryo kayması.

    freqtrade --fee her işlem bacağına bir kez uygulanır; kayma tek yön bps olarak
    komisyona eklenir (muhafazakâr model: tüm girişler taker).
    """
    if scenario not in SCENARIO_KEYS:
        raise ValueError(
            f"tanımsız senaryo: {scenario!r}; geçerli: {sorted(SCENARIO_KEYS)} (CR-5 matrisi)"
        )
    bps = costs["stress_scenarios"][SCENARIO_KEYS[scenario]]
    if not isinstance(bps, int | float) or bps < 0:
        raise ValueError(f"senaryo bps mantıksız: {bps!r}")
    return float(costs["fees"]["taker"]) + float(bps) / 10_000.0
