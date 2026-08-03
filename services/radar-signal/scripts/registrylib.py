"""Experiment Registry — append-only JSONL (CLAUDE.md kural 8; CR-002 P0-2).

Her backtest/hyperopt/varyant koşusu buraya yazılır; yazılamazsa koşu GEÇERSİZDİR.
Kayıt git'e girer (`registry/experiments.jsonl`) — kanıt zinciri repoda yaşar.

Şema v2 alanları (P0-2 tam seti):
    experiment_id, schema_version, created_at_utc, hypothesis_id, strategy,
    strategy_version (git commit), param_hash, dataset_snapshot, cost_model_version,
    scenario, effective_fee, timerange, timeframe_detail, result, verdict, parent,
    created_by, pairs, provenance (lockfile/config hash'leri — ŞART A)

`verdict` dört temel değer alır: `pending`, `accepted`, `rejected`, `invalid`.
Reddedilen/geçersiz koşu SİLİNMEZ — yayın yanlılığına karşı iç önlem (SINYAL-SPEC §3.5).

DSR'a giren N buradan gelir: `trials_for_dsr(hypothesis_id)`. Elle sayı girmek yasaktır.
"""

import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO / "registry" / "experiments.jsonl"
MANIFEST_DIR = REPO / "docs" / "data"
STRATEGY_DIR = REPO / "user_data" / "strategies"

SCHEMA_VERSION = "2"
VALID_VERDICTS = ("pending", "accepted", "rejected", "invalid")
VALID_CREATORS = ("insan", "claude", "codex")
REQUIRED_FIELDS = ("hypothesis_id", "strategy", "scenario", "effective_fee", "exit_code")


def git_commit_hash() -> str:
    """Signal servis ağacını en son değiştiren commit'in kısa SHA'sı."""
    sys.path.insert(0, str(REPO / "scripts"))
    from provenance import git_commit

    return git_commit()


def latest_manifest_hash() -> str:
    """En yeni veri manifestinin sha256'sı (ŞART B: dataset_snapshot buraya işaret eder)."""
    manifests = sorted(MANIFEST_DIR.glob("MANIFEST-*.json"))
    if not manifests:
        raise FileNotFoundError(
            "veri manifesti yok; önce scripts/data_manifest.py koş (kayıtsız koşu geçersiz)"
        )
    doc = json.loads(manifests[-1].read_text(encoding="utf-8"))
    return doc["manifest_sha256"]


def param_hash(strategy: str) -> str | None:
    """Parametre JSON'unun hash'i — aynı kod + farklı parametre ayırt edilir."""
    path = STRATEGY_DIR / f"{strategy}.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(doc.get("params", {}), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def cost_model_version() -> str:
    return hashlib.sha256((REPO / "config" / "costs.yaml").read_bytes()).hexdigest()[:12]


def _provenance() -> dict:
    """Ortam parmak izi (ŞART A). Alınamazsa koşu engellenmez, eksiklik kaydedilir."""
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        from provenance import environment_fingerprint

        return environment_fingerprint()
    except Exception as exc:
        return {"error": f"parmak izi alınamadı: {type(exc).__name__}"}


def record_run(*, registry_path: Path | None = None, **fields) -> dict:
    """Koşuyu kayda geçir; kaydı döndür. Eksik zorunlu alan → ValueError (fail-loud)."""
    for required in REQUIRED_FIELDS:
        if required not in fields:
            raise ValueError(f"registry kaydı eksik alan: {required}")

    verdict = fields.pop("verdict", "pending")
    verdict_base = verdict.split()[0].lower()
    if verdict_base not in VALID_VERDICTS:
        raise ValueError(f"geçersiz verdict: {verdict!r}; izinli: {VALID_VERDICTS}")
    created_by = fields.pop("created_by", "claude")
    if created_by not in VALID_CREATORS:
        raise ValueError(f"geçersiz created_by: {created_by!r}; izinli: {VALID_CREATORS}")

    pairs = fields.pop("pairs", None)

    entry = {
        "experiment_id": f"E-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "strategy_version": git_commit_hash(),
        "param_hash": param_hash(fields["strategy"]),
        "dataset_snapshot": latest_manifest_hash(),
        "cost_model_version": cost_model_version(),
        "verdict": verdict,
        "pairs": pairs,
        "parent": fields.pop("parent", None),
        "created_by": created_by,
        "provenance": _provenance(),
        **fields,
    }
    path = registry_path or REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def update_verdict(
    experiment_id: str, verdict: str, reason: str | None = None, registry_path: Path | None = None
) -> bool:
    """Belirtilen experiment_id'nin verdict'ini güncelle (kaydı korur)."""
    path = registry_path or REGISTRY_PATH
    if not path.exists():
        return False
    rows = read_all(path)
    updated = False
    new_rows = []
    for r in rows:
        if r.get("experiment_id") == experiment_id:
            r["verdict"] = verdict
            if reason:
                r["verdict_reason"] = reason
            updated = True
        new_rows.append(r)
    if updated:
        with path.open("w", encoding="utf-8") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return updated


def read_all(registry_path: Path | None = None) -> list[dict]:
    path = registry_path or REGISTRY_PATH
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def count_runs(strategy_family: str, registry_path: Path | None = None) -> int:
    return sum(1 for e in read_all(registry_path) if e.get("hypothesis_id") == strategy_family)


def trials_for_dsr(strategy_family: str, registry_path: Path | None = None) -> int:
    n = count_runs(strategy_family, registry_path)
    if n < 2:
        raise ValueError(
            f"'{strategy_family}' için registry'de {n} koşu var; DSR ≥2 deneme ister. "
            "Önce koşuları kaydet (kayıtsız koşu geçersizdir)."
        )
    return n
