"""Veri bütünlük manifesti üretir (onay ŞART B).

user_data/data/binance altındaki her veri dosyası için: sha256, satır sayısı,
tarih aralığı. Çıktı: docs/data/MANIFEST-<YYYYMMDD>.md + .json.
Experiment Registry'nin `dataset_snapshot` alanı bu manifestin sha256'sına işaret eder.

Kullanım: .venv/Scripts/python scripts/data_manifest.py
"""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "user_data" / "data" / "binance"
OUT_DIR = REPO / "docs" / "data"


def file_entry(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    df = pd.read_feather(path)
    if "date" not in df.columns:
        raise ValueError(f"{path.name}: 'date' kolonu yok — beklenmeyen veri formatı")
    return {
        "file": str(path.relative_to(REPO)).replace("\\", "/"),
        "sha256": digest,
        "rows": int(len(df)),
        "date_min_utc": df["date"].min().isoformat(),
        "date_max_utc": df["date"].max().isoformat(),
    }


def main() -> None:
    if not DATA_DIR.is_dir():
        sys.exit(f"HATA: veri dizini yok: {DATA_DIR}")
    files = sorted(DATA_DIR.rglob("*.feather"))
    if not files:
        sys.exit("HATA: hiç .feather dosyası bulunamadı; önce download-data koş")

    entries = [file_entry(p) for p in files]
    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "exchange": "binance",
        "trading_mode": "futures",
        "files": entries,
    }
    blob = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    manifest_hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = manifest_hash

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    json_path = OUT_DIR / f"MANIFEST-{stamp}.json"
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        f"# Veri Bütünlük Manifesti — {stamp}",
        "",
        f"- Üretim: {manifest['generated_at_utc']}",
        f"- Manifest sha256 (Registry `dataset_snapshot` bu değere işaret eder): `{manifest_hash}`",
        "",
        "| Dosya | Satır | Aralık (UTC) | sha256 (ilk 16) |",
        "|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e['file']} | {e['rows']} | {e['date_min_utc'][:10]} → {e['date_max_utc'][:10]} "
            f"| `{e['sha256'][:16]}` |"
        )
    md_path = OUT_DIR / f"MANIFEST-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: {json_path.name} + {md_path.name} · manifest_sha256={manifest_hash[:16]}...")


if __name__ == "__main__":
    main()
