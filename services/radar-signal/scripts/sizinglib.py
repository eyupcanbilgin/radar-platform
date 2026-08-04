"""Pozisyon boyutlandırma yardımcısı — `config/sizing.yaml` tek kaynak.

Stratejiler oranı kendi içlerinde sabitlemez; buradan okur. Böylece boyutlandırma
politikası tek yerden değişir ve yeni bir strateji "sabit notional" tuzağına
düşmeden doğru varsayılanı miras alır.
"""

from pathlib import Path

import yaml

SERVICE_ROOT = Path(__file__).resolve().parent.parent
SIZING_PATH = SERVICE_ROOT / "config" / "sizing.yaml"


def load_sizing(path: Path | None = None) -> dict:
    p = path or SIZING_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p.name} boş ya da dict değil")
    pct = raw.get("stake_pct_of_wallet")
    if not isinstance(pct, int | float) or not 0 < pct <= 1.0:
        raise ValueError(f"stake_pct_of_wallet (0,1] aralığında olmalı; gelen: {pct!r}")
    floor = raw.get("min_stake_fallback")
    if not isinstance(floor, int | float) or floor <= 0:
        raise ValueError(f"min_stake_fallback > 0 olmalı; gelen: {floor!r}")
    return raw


def wallet_pct_stake(wallet_total: float, min_stake: float | None, sizing: dict) -> float:
    """Cüzdanın yapılandırılmış yüzdesi; borsa min_stake'i altına düşmez."""
    if wallet_total < 0:
        raise ValueError(f"cüzdan negatif olamaz: {wallet_total}")
    floor = min_stake if min_stake is not None else float(sizing["min_stake_fallback"])
    return max(wallet_total * float(sizing["stake_pct_of_wallet"]), floor)
