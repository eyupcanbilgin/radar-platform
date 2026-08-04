"""Veri yolu çözümlemesi — tek kaynak.

Ham piyasa verisi `.gitignore`'dadır; makineden makineye yeri değişebilir. Yolu koda
gömmek yerine tek yerden çözülür:

    1. `RADAR_SIGNAL_USERDIR` ortam değişkeni (varsa)
    2. servis kökündeki `user_data/` (varsayılan)

Monorepo birleşmesinde (4 Ağu 2026) veri, eski `projeler/radar-signal` altında kalmıştı
ve monorepoda backtest koşulamıyordu. Bu modül o sınıf hatayı tekrarlamamak için var:
"manifest var ama veri yok" durumu artık sessiz kalmaz (bkz. `verify_manifest`).
"""

import hashlib
import json
import os
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = SERVICE_ROOT / "docs" / "data"


def user_dir() -> Path:
    env = os.environ.get("RADAR_SIGNAL_USERDIR")
    if env:
        return Path(env)
    return SERVICE_ROOT / "user_data"


def data_dir() -> Path:
    return user_dir() / "data" / "binance"


def results_dir() -> Path:
    return user_dir() / "backtest_results"


def latest_manifest_path() -> Path | None:
    manifests = sorted(MANIFEST_DIR.glob("MANIFEST-*.json"))
    return manifests[-1] if manifests else None


def verify_manifest(manifest_path: Path | None = None) -> dict:
    """Manifestteki her dosyanın diskte VAR olduğunu ve sha256'sının tuttuğunu doğrular.

    Döner: {"status": ok|missing_manifest|missing_data|hash_mismatch, "missing": [...],
            "mismatched": [...], "checked": n}

    `status != "ok"` olması manifestin gerçeği yansıtmadığı anlamına gelir — kayıtlarda
    `dataset_snapshot` bu manifestin hash'ine işaret ettiği için, tutmayan bir manifest
    tüm kanıt zincirini şüpheli hale getirir.
    """
    path = manifest_path or latest_manifest_path()
    if path is None:
        return {"status": "missing_manifest", "missing": [], "mismatched": [], "checked": 0}

    doc = json.loads(path.read_text(encoding="utf-8"))
    base = user_dir().parent  # manifest yolları servis köküne göreli yazılır
    missing, mismatched = [], []
    for entry in doc.get("files", []):
        rel = entry["file"]
        candidate = base / rel
        if not candidate.exists():
            # RADAR_SIGNAL_USERDIR ile taşınmış olabilir: user_data/ önekini yeniden kur
            alt = user_dir() / Path(rel).relative_to("user_data")
            candidate = alt if alt.exists() else candidate
        if not candidate.exists():
            missing.append(rel)
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            mismatched.append(rel)

    total = len(doc.get("files", []))
    if missing and len(missing) == total:
        # Hiçbir veri dosyası yok: ham veri git dışı olduğu için CI runner'ının normal
        # hâli budur. "Kısmen eksik"ten AYRI bir durum olarak raporlanır; ikisini aynı
        # kefeye koymak CI'ı kalıcı kırmızıya çevirir ve kontrolü işlevsizleştirirdi.
        status = "no_data"
    elif missing:
        status = "missing_data"
    elif mismatched:
        status = "hash_mismatch"
    else:
        status = "ok"
    return {
        "status": status,
        "missing": missing,
        "mismatched": mismatched,
        "checked": len(doc.get("files", [])),
        "manifest": path.name,
    }
