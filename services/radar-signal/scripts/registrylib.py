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
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO / "registry" / "experiments.jsonl"
VERDICT_EVENTS_PATH = REPO / "registry" / "verdict_events.jsonl"
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
    _append_line(path, json.dumps(entry, ensure_ascii=False, sort_keys=True))
    return entry


def _events_path(registry_path: Path, verdict_events_path: Path | None = None) -> Path:
    if verdict_events_path is not None:
        return verdict_events_path
    if registry_path == REGISTRY_PATH:
        return VERDICT_EVENTS_PATH
    return registry_path.with_name("verdict_events.jsonl")


def _verdict_base(verdict: str) -> str:
    base = verdict.split()[0].lower()
    if base not in VALID_VERDICTS:
        raise ValueError(f"geçersiz verdict: {verdict!r}; izinli: {VALID_VERDICTS}")
    return base


def update_verdict(
    experiment_id: str,
    verdict: str,
    reason: str | None = None,
    registry_path: Path | None = None,
    verdict_events_path: Path | None = None,
    created_by: str = "claude",
) -> bool:
    """Append an immutable verdict event; never rewrite the experiment registry."""
    _verdict_base(verdict)
    if created_by not in VALID_CREATORS:
        raise ValueError(f"geçersiz created_by: {created_by!r}; izinli: {VALID_CREATORS}")
    path = registry_path or REGISTRY_PATH
    if not path.exists():
        return False
    events_path = _events_path(path, verdict_events_path)
    rows = read_all(path, verdict_events_path=events_path)
    current = next((row for row in rows if row.get("experiment_id") == experiment_id), None)
    if current is None:
        return False
    event = {
        "event_id": f"V-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
        "schema_version": "1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "experiment_id": experiment_id,
        "previous_verdict": current.get("verdict"),
        "verdict": verdict,
        "reason": reason,
        "created_by": created_by,
    }
    _append_line(events_path, json.dumps(event, ensure_ascii=False, sort_keys=True))
    return True


# --- Encoding savunma katmanı -----------------------------------------------------------
# 4 Ağu 2026: registry'nin 7 satırı repo dışı bir araç tarafından Windows ANSI kod
# sayfasıyla (cp1254) yeniden yazıldı; read_all() UnicodeDecodeError ile çöktü ve DSR
# dahil tüm çoklu-deneme düzeltmesi devre dışı kaldı. Yazan araç bilinmiyor (repodaki
# tüm Python yazımları utf-8 belirtiyordu), bu yüzden savunma iki taraflı kuruldu:
# yazarken encoding+newline açıkça sabitlenir, okurken bozuk bayt fail-loud raporlanır.


def _append_line(path: Path, line: str) -> None:
    # newline="\n": Windows'ta CRLF'e çevrilmeyi engeller (JSONL satır bütünlüğü)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def verify_encoding(registry_path: Path | None = None) -> list[int]:
    """UTF-8 olarak çözülemeyen satır numaralarını döndürür (1-tabanlı). Boş liste = temiz."""
    path = registry_path or REGISTRY_PATH
    if not path.exists():
        return []
    bad = []
    for i, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(i)
    return bad


class RegistryEncodingError(Exception):
    """Registry dosyası UTF-8 değil — okuma reddedildi (sessiz fallback yapılmaz)."""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    bad = verify_encoding(path)
    if bad:
        raise RegistryEncodingError(
            f"{path.name}: {len(bad)} satır UTF-8 değil (satırlar: {bad}). "
            "Onarım: python scripts/repair_registry_encoding.py --apply"
        )
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def read_verdict_events(
    registry_path: Path | None = None,
    verdict_events_path: Path | None = None,
) -> list[dict]:
    path = registry_path or REGISTRY_PATH
    return _read_jsonl(_events_path(path, verdict_events_path))


def read_all(
    registry_path: Path | None = None,
    verdict_events_path: Path | None = None,
) -> list[dict]:
    """Tüm kayıtları oku.

    Bozuk baytta SESSİZCE başka bir kod sayfasına düşülmez: yanlış çözülen bir kayıt
    kanıt zincirini görünmez biçimde bozardı. Bunun yerine hangi satırların bozuk
    olduğu ve nasıl onarılacağı söylenir (fail-loud, CLAUDE.md kural 2).
    """
    path = registry_path or REGISTRY_PATH
    rows = _read_jsonl(path)
    by_id = {row.get("experiment_id"): row for row in rows}
    for event in read_verdict_events(path, verdict_events_path):
        experiment_id = event.get("experiment_id")
        if experiment_id not in by_id:
            raise ValueError(f"verdict event bilinmeyen deney kimliğine bağlı: {experiment_id!r}")
        row = deepcopy(by_id[experiment_id])
        row.setdefault("initial_verdict", row.get("verdict"))
        row["verdict"] = event["verdict"]
        if event.get("reason"):
            row["verdict_reason"] = event["reason"]
        row["verdict_event_id"] = event["event_id"]
        row["verdict_updated_at_utc"] = event["created_at_utc"]
        by_id[experiment_id] = row
    return [by_id[row.get("experiment_id")] for row in rows]


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


def unique_phase2_trials_for_dsr(registry_path: Path | None = None) -> list[dict]:
    """Return canonical Phase-2 evidence trials for the global data-mining penalty.

    Old backtests without a structured result are outside the current protocol. Effective
    ``invalid`` rows (including duplicate reruns) are excluded, then the evidence identity
    is deduplicated by hypothesis, code SHA and dataset snapshot.
    """
    unique: dict[tuple[str, str, str], dict] = {}
    for row in read_all(registry_path):
        if _verdict_base(str(row.get("verdict", "invalid"))) == "invalid":
            continue
        if row.get("exit_code") != 0 or not isinstance(row.get("result"), dict):
            continue
        identity = (
            str(row.get("hypothesis_id", "")),
            str(row.get("strategy_version", "")),
            str(row.get("dataset_snapshot", "")),
        )
        if not all(identity):
            raise ValueError(f"Faz 2 kanıt kimliği eksik: {row.get('experiment_id')}")
        unique.setdefault(identity, row)
    return [unique[key] for key in sorted(unique)]


def phase2_trial_count_for_dsr(registry_path: Path | None = None) -> int:
    return len(unique_phase2_trials_for_dsr(registry_path))
