"""Experiment Registry v0 — append-only JSONL (CLAUDE.md kural 8; CR-002 P0-2'nin çekirdeği).

Her backtest koşusu buraya yazılır; yazılamazsa koşu GEÇERSİZDİR (bt.py çıkış koduna yansır).
Kayıt git'e girer (registry/experiments.jsonl) — kanıt zinciri repoda yaşar.
Tam şema (param_hash, parent, DSR N bağlantısı) İ-8'de tamamlanır.
"""

import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO / "registry" / "experiments.jsonl"
MANIFEST_DIR = REPO / "docs" / "data"


def git_commit_hash() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def latest_manifest_hash() -> str:
    """En yeni veri manifestinin sha256'sı (ŞART B: dataset_snapshot buraya işaret eder)."""
    manifests = sorted(MANIFEST_DIR.glob("MANIFEST-*.json"))
    if not manifests:
        raise FileNotFoundError(
            "veri manifesti yok; önce scripts/data_manifest.py koş (kayıtsız koşu geçersiz)"
        )
    doc = json.loads(manifests[-1].read_text(encoding="utf-8"))
    return doc["manifest_sha256"]


def record_run(*, registry_path: Path | None = None, **fields) -> dict:
    """Koşuyu kayda geçir; kaydı döndür. Eksik zorunlu alan → ValueError (fail-loud)."""
    for required in ("strategy", "hypothesis_id", "scenario", "effective_fee", "exit_code"):
        if required not in fields:
            raise ValueError(f"registry kaydı eksik alan: {required}")
    entry = {
        "experiment_id": f"E-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "strategy_version": git_commit_hash(),
        "dataset_snapshot": latest_manifest_hash(),
        "created_by": "claude",
        **fields,
    }
    path = registry_path or REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def count_runs(strategy_family: str, registry_path: Path | None = None) -> int:
    """DSR'a girecek N: aile için registry'deki gerçek toplam deneme sayısı (P0-2)."""
    path = registry_path or REGISTRY_PATH
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("hypothesis_id") == strategy_family:
            n += 1
    return n
