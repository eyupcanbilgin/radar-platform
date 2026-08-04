"""Registry encoding onarım aracı — tek seferlik, idempotent, kayıpsız.

## Neden var

`registry/experiments.jsonl` dosyasının 8–14. satırları Windows ANSI kod sayfasıyla
(cp1254, Türkçe) yazılmış; UTF-8 olarak okunamıyordu ve `registrylib.read_all()`
`UnicodeDecodeError` ile çöküyordu. Bu, `count_runs`/`trials_for_dsr`/`update_verdict`
zincirini — yani DSR dahil tüm çoklu-deneme düzeltmesini — devre dışı bırakmıştı.

## Kök neden (kanıt)

Bozulma `5fa5c50` commit'inde girdi (`ff113d8`'de dosya 7 satır ve UTF-8 temizdi).
O commit'te registry'ye 7 S-0002 kaydı eklendi ve verdict'leri `INVALID` yapıldı.
İmza şu: **yalnız Türkçe karakter içeren satırlar bozuk; saf ASCII satırlar (1-7)
sağlam.** Bu, dosyanın tamamının ANSI kod sayfasıyla yeniden yazıldığını gösterir —
ASCII baytları değişmez, yalnız non-ASCII olanlar bozulur.

**Yazan araç bilinmiyor.** Repodaki tüm Python yazımları `encoding="utf-8"` belirtiyor
(`record_run`, `update_verdict`, `data_manifest`), dolayısıyla bozulma repo dışı bir
araçtan geldi — büyük olasılıkla IDE/ajan dosya yazımı ya da PowerShell 5.1
`Set-Content`/`Out-File` (varsayılanı ANSI'dir). Kanıt yetersiz olduğu için tek bir
araç suçlanmıyor; savunma kod tarafında kuruldu (bkz. `registrylib.verify_encoding`).

## Kullanım

    python scripts/repair_registry_encoding.py --check     # yalnız rapor, yazmaz
    python scripts/repair_registry_encoding.py --apply     # onarır (yedek alır)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "registry" / "experiments.jsonl"

# Bozulmanın kaynağı: Windows Türkçe ANSI kod sayfası. cp1252 ile de denenir çünkü
# ikisi yalnız birkaç baytta ayrışır ve yanlış seçim sessiz karakter bozulması yaratır.
CANDIDATE_ENCODINGS = ("cp1254", "cp1252")


def scan(path: Path) -> tuple[list[int], list[bytes]]:
    """(bozuk satır numaraları, tüm satırlar) döndürür. 1-tabanlı numaralandırma."""
    lines = path.read_bytes().splitlines()
    bad = []
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            ln.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(i)
    return bad, lines


def repair_line(raw: bytes) -> tuple[str, str]:
    """Bozuk satırı çöz; (metin, kullanılan_encoding) döndürür.

    Çözülen metnin geçerli JSON olduğu doğrulanır — aksi halde yanlış kod sayfası
    seçilmiş demektir ve sessizce bozuk veri yazmaktansa hata fırlatılır.
    """
    for enc in CANDIDATE_ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError:
            continue
        return text, enc
    raise ValueError(
        f"satır hiçbir aday kod sayfasıyla geçerli JSON'a çözülemedi: {CANDIDATE_ENCODINGS}"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="yalnız rapor")
    g.add_argument("--apply", action="store_true", help="onar (önce .bak yedeği alır)")
    ap.add_argument("--path", type=Path, default=REGISTRY)
    args = ap.parse_args()

    path = args.path
    if not path.exists():
        sys.exit(f"HATA: registry yok: {path}")

    bad, lines = scan(path)
    if not bad:
        print(f"OK: {path.name} tamamen UTF-8 ({len(lines)} satır). Yapılacak iş yok.")
        return

    print(f"BOZUK: {len(bad)}/{len(lines)} satır UTF-8 değil → {bad}")
    repaired: list[str] = []
    used: set[str] = set()
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        if i in bad:
            text, enc = repair_line(ln)
            used.add(enc)
            repaired.append(text)
        else:
            repaired.append(ln.decode("utf-8"))

    print(f"Çözümde kullanılan kod sayfası: {sorted(used)}")
    if args.check:
        print("--check modu: dosya değiştirilmedi.")
        # Onarımın sonucunu göster ki insan doğrulayabilsin
        for i in bad[:3]:
            entry = json.loads(repaired[i - 1])
            print(f"  satır {i}: verdict = {entry.get('verdict')!r}")
        sys.exit(1)  # CI'da kırmızı

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    # newline="\n": Windows'ta CRLF'e çevrilmesini engeller (JSONL satır bütünlüğü)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for text in repaired:
            f.write(text + "\n")

    still_bad, _ = scan(path)
    if still_bad:
        shutil.copy2(backup, path)
        sys.exit(f"HATA: onarım sonrası hâlâ bozuk satır var {still_bad}; yedekten geri alındı")
    print(f"ONARILDI: {len(bad)} satır UTF-8'e çevrildi. Yedek: {backup.name}")
    print(f"Doğrulama: {len(repaired)} kayıt okunabiliyor.")


if __name__ == "__main__":
    main()
