"""Fail-closed kapısı — CR-002 P0-8'in kesin tanımı.

    zorunlu girdi eksik            → BLOCK (sinyal gitmez)
    opsiyonel katman erişilemez    → sinyal GİDER, ama etiketlenir ve defterde
                                      ayrı bayrak taşır (defterde ayrı izlenir)

Hangi girdinin zorunlu olduğu `config/lifecycle.yaml`'da; koda gömülmez.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
LIFECYCLE_PATH = REPO / "config" / "lifecycle.yaml"


def load_lifecycle(path: Path | None = None) -> dict:
    p = path or LIFECYCLE_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p.name} boş ya da dict değil")
    for key in (
        "version",
        "inputs",
        "degraded_flags",
        "validity",
        "exit_precedence",
        "outbox",
        "webhook_auth",
    ):
        if key not in raw:
            raise ValueError(f"lifecycle.yaml eksik alan: {key}")
    if not raw["inputs"].get("required"):
        raise ValueError("inputs.required boş olamaz — fail-closed anlamsızlaşır")
    auth = raw["webhook_auth"]
    for key in ("max_clock_skew_seconds", "nonce_retention_seconds"):
        value = auth.get(key) if isinstance(auth, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"webhook_auth.{key} pozitif integer olmalı")
    return raw


@dataclass(frozen=True)
class GateResult:
    approved: bool
    block_reason: str | None
    degraded_flags: list[str]  # opsiyonel eksiklerin kullanıcıya görünen etiketleri
    degraded_inputs: list[str]  # defterde izlenecek makine-okur adlar


def evaluate_inputs(available: dict[str, bool], lifecycle: dict) -> GateResult:
    """Girdi durumuna göre sinyalin geçip geçmeyeceğine karar verir.

    `available`: girdi adı → erişilebilir mi. Listede hiç görünmeyen zorunlu girdi
    "eksik" sayılır (sessiz varsayım yok).
    """
    required = list(lifecycle["inputs"]["required"])
    optional = list(lifecycle["inputs"].get("optional") or [])
    flags_map = lifecycle["degraded_flags"]

    missing_required = [name for name in required if not available.get(name, False)]
    if missing_required:
        return GateResult(
            approved=False,
            block_reason=(
                "ZORUNLU GİRDİ EKSİK: "
                + ", ".join(sorted(missing_required))
                + " — sinyal üretilmedi"
            ),
            degraded_flags=[],
            degraded_inputs=[],
        )

    degraded = [name for name in optional if not available.get(name, False)]
    unknown_flag = [name for name in degraded if name not in flags_map]
    if unknown_flag:
        raise ValueError(
            f"degraded_flags'te etiketi olmayan opsiyonel girdi: {unknown_flag} "
            "— config/lifecycle.yaml güncellenmeli (etiketsiz sessiz düşüş yasak)"
        )
    return GateResult(
        approved=True,
        block_reason=None,
        degraded_flags=[flags_map[name] for name in sorted(degraded)],
        degraded_inputs=sorted(degraded),
    )
