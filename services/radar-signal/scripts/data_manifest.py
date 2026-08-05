"""Veri bütünlük manifesti üretir ve doğrular (onay ŞART B).

Veri dizinindeki her dosya için: sha256, satır sayısı, tarih aralığı.
Çıktı: docs/data/MANIFEST-<YYYYMMDD>.md + .json. Experiment Registry'nin
`dataset_snapshot` alanı bu manifestin sha256'sına işaret eder.

Veri yolu `scripts/datapaths.py` üzerinden çözülür (`RADAR_SIGNAL_USERDIR` ile
override edilebilir).

Kullanım:
    python scripts/data_manifest.py            # manifest üret
    python scripts/data_manifest.py --verify   # manifest ↔ diskteki veri eşleşiyor mu
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datapaths import market_data_root, verify_manifest  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
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


def run_verify(allow_missing_data: bool) -> None:
    """Manifest ↔ diskteki veri eşleşmesini doğrular.

    Üç sonuç sınıfı ayrı tutulur, çünkü hepsini "hata" saymak CI'ı kalıcı kırmızıya
    çevirir ve kontrolü işlevsizleştirir:
      ok           → her dosya yerinde ve hash tutuyor
      no_data      → HİÇ veri yok (ham veri git dışı; CI runner'ının normal hâli)
      missing_data → veri KISMEN var: manifest gerçeği yansıtmıyor → her zaman hata
      hash_mismatch→ dosya değişmiş → her zaman hata
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = verify_manifest()
    status = report["status"]

    if status == "ok":
        print(f"OK: {report['manifest']} · {report['checked']} dosya yerinde, hash tutuyor")
        return
    if status == "missing_manifest":
        print("UYARI: hiç manifest yok — doğrulanacak bir şey yok")
        return
    if status == "no_data":
        msg = f"{report['manifest']} · {report['checked']} dosyanın hiçbiri diskte yok"
        if allow_missing_data:
            print(f"ATLANDI: {msg} (ham veri git dışı; --allow-missing-data verildi)")
            return
        sys.exit(
            f"BAŞARISIZ (no_data): {msg}.\n"
            "Manifest var ama veri yok: bu ortamda backtest koşulamaz. Veriyi indir "
            "(make download-data), RADAR_SIGNAL_USERDIR ile yol ver ya da CI'daysan "
            "--allow-missing-data kullan."
        )

    print(f"BAŞARISIZ ({status}) · manifest: {report['manifest']}")
    for rel in report["missing"]:
        print(f"  EKSİK VERİ: {rel}")
    for rel in report["mismatched"]:
        print(f"  HASH TUTMUYOR: {rel}")
    sys.exit(
        "Manifest gerçeği yansıtmıyor. Registry kayıtlarındaki `dataset_snapshot` bu "
        "manifeste işaret ettiği için kanıt zinciri şüphelidir: veriyi getir ya da "
        "manifesti yeniden üret (bkz. docs/data/OKUBENI.md)."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--verify", action="store_true", help="üretme, manifest↔veri eşleşmesini denetle"
    )
    ap.add_argument(
        "--allow-missing-data",
        action="store_true",
        help="verinin TAMAMEN yokluğunu hata sayma (CI); kısmi eksik ve hash sapması yine hata",
    )
    args = ap.parse_args()
    if args.verify:
        run_verify(args.allow_missing_data)
        return

    data_path = market_data_root()
    if not data_path.is_dir():
        sys.exit(f"HATA: veri dizini yok: {data_path} (RADAR_SIGNAL_USERDIR ile yol verilebilir)")
    files = sorted(data_path.rglob("*.feather"))
    if not files:
        sys.exit("HATA: hiç .feather dosyası bulunamadı; önce download-data koş")

    entries = [file_entry(p) for p in files]
    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": "multi_venue_market_data",
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
