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


#: Koşunun KENDİSİNİN yazması beklenen append-only kanıt kütükleri.
#:
#: Bunları kirlilik saymak bayrağı kendi kendini yenen bir kontrole çevirir: her gerçek
#: ölçüm Registry'ye satır yazar, dolayısıyla `git_dirty` hiçbir koşuda False olamaz ve
#: "kanıt üreten koşu temiz ağaçta yapılır" kuralı (ADR-0003, Platform ADR-0004,
#: CLAUDE.md kural 13) fiilen hiçbir şeyi korumaz.
#:
#: 10 Ağustos 2026'da ölçüldü: S-0003, S-0004 ve S-0005 koşularının HEPSİ `git_dirty=true`
#: kaydetmişti; yalnız `registry/experiments.jsonl` değiştirildiğinde de bayrak True
#: dönüyordu. Kütükleri hariç tutmak bayrağı asıl işine döndürür — değişmiş kaynak, config
#: veya hipotez kartı hâlâ kirlilik sayılır.
EVIDENCE_LOGS: tuple[str, ...] = (
    "registry/experiments.jsonl",
    "registry/verdict_events.jsonl",
)


def _porcelain_paths(line: str) -> list[str]:
    """`git status --porcelain` satırından yol(lar)ı çıkar; rename iki yol taşır."""
    payload = line[3:].strip()
    if " -> " in payload:
        return [part.strip().strip('"') for part in payload.split(" -> ", 1)]
    return [payload.strip('"')]


def _is_evidence_log(path: str, ignore: tuple[str, ...]) -> bool:
    """Yol muaf kütüklerden biri mi — dizin sınırına saygı göstererek.

    Düz ``endswith`` yetmez: ``evil-registry/experiments.jsonl`` da eşleşir ve muafiyet,
    korumadan kaçmak için kullanılabilecek bir açığa dönerdi. Eşleşme ya tam yol olmalı ya
    da bir ``/`` sınırından sonra gelmelidir.
    """
    return any(path == suffix or path.endswith(f"/{suffix}") for suffix in ignore)


def git_is_dirty(*, ignore: tuple[str, ...] = EVIDENCE_LOGS) -> bool:
    """Ağaçta, koşunun yazması beklenen kanıt kütükleri DIŞINDA değişiklik var mı.

    ``ignore`` boş verilirse ham git davranışına dönülür; testler bunu kullanır.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal", "--", "."],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        paths = _porcelain_paths(line)
        if paths and all(_is_evidence_log(path, ignore) for path in paths):
            continue
        return True
    return False


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
