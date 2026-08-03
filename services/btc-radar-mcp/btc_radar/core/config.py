"""config/ dizinini bulur, YAML'ları yükler ve Pydantic ile fail-loud doğrular.

Çözüm sırası:
1. BTC_RADAR_CONFIG_DIR ortam değişkeni (test/dağıtım override'ı)
2. Repo kökündeki config/ (geliştirme: uv run btc-radar)
3. Paket içine gömülü btc_radar/_config (dağıtım: uvx --from . btc-radar)
"""

import hashlib
import os
from pathlib import Path

import yaml

from btc_radar.models.config import SignalRulesConfig, WeightsConfig

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    env = os.environ.get("BTC_RADAR_CONFIG_DIR")
    if env:
        p = Path(env)
        if not p.is_dir():
            raise FileNotFoundError(f"BTC_RADAR_CONFIG_DIR geçersiz bir dizin gösteriyor: {env}")
        return p
    repo = _PACKAGE_ROOT.parent / "config"
    if repo.is_dir():
        return repo
    packaged = _PACKAGE_ROOT / "_config"
    if packaged.is_dir():
        return packaged
    raise FileNotFoundError(
        "config dizini bulunamadı; BTC_RADAR_CONFIG_DIR tanımla veya repo kökünden çalıştır"
    )


def _load_yaml(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} boş ya da beklenen yapıda değil (dict bekleniyor)")
    return raw


def load_weights(path: Path | None = None) -> WeightsConfig:
    p = path or config_dir() / "weights.yaml"
    return WeightsConfig.model_validate(_load_yaml(p))


def load_signal_rules(path: Path | None = None) -> SignalRulesConfig:
    p = path or config_dir() / "signal_rules.yaml"
    return SignalRulesConfig.model_validate(_load_yaml(p))


def weights_hash(path: Path | None = None) -> str:
    """weights.yaml içeriğinin sha256 kısa hash'i — skor izlenebilirliği (SPEC §5.2)."""
    p = path or config_dir() / "weights.yaml"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
