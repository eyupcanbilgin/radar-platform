"""Çalışma ortamı parmak izi — "bu sonucu hangi dünyada ürettik" sorusunun cevabı.

Replay determinizmi yalnız aynı veriyi değil aynı ORTAMI de gerektirir: bir bağımlılık
sürümü değiştiğinde (ör. pandas yuvarlama davranışı) aynı girdi farklı sonuç verebilir.
Bu yüzden `requirements.lock` hash'i determinizm kaydının parçasıdır (onay ŞART A).

Parmak izi bileşenleri:
    git_commit      — signal servisini en son değiştiren commit
    lockfile_sha256 — bağımlılık kilidi (ŞART A)
    costs_sha256    — maliyet modeli
    lifecycle_sha256— yaşam döngüsü politikası
    dataset_snapshot— veri manifesti (ŞART B)
"""

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCKFILE = REPO / "requirements.lock"
MANIFEST_DIR = REPO / "docs" / "data"


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"parmak izi için gerekli dosya yok: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lockfile_hash() -> str:
    """requirements.lock'un tam sha256'sı (ŞART A)."""
    return _sha256_file(LOCKFILE)


def git_commit() -> str:
    """Signal servis ağacını en son değiştiren commit'in kısa SHA'sı.

    Monorepoda yalnız MCP veya kök doküman değiştiğinde strateji sürümü değişmemelidir.
    """
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "."],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()[:12]


def git_is_dirty() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal", "--", "."],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(out.stdout.strip())


def dataset_snapshot() -> str:
    manifests = sorted(MANIFEST_DIR.glob("MANIFEST-*.json"))
    if not manifests:
        raise FileNotFoundError("veri manifesti yok; önce scripts/data_manifest.py koş")
    return json.loads(manifests[-1].read_text(encoding="utf-8"))["manifest_sha256"]


def environment_fingerprint() -> dict:
    """Determinizm kaydının ortam bölümü. `dirty` True ise sonuç 'final' etiketi alamaz."""
    return {
        "git_commit": git_commit(),
        "git_dirty": git_is_dirty(),
        "lockfile_sha256": lockfile_hash(),
        "costs_sha256": _sha256_file(REPO / "config" / "costs.yaml"),
        "lifecycle_sha256": _sha256_file(REPO / "config" / "lifecycle.yaml"),
        "dataset_snapshot": dataset_snapshot(),
    }
