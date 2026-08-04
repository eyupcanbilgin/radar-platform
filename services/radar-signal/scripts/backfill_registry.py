"""Registry geriye doldurma — `pairs` alanı ve kapanmamış `verdict`'ler.

## Neden var

- `pairs` alanı registry şemasına S-0002b sırasında eklendi; önceki 14 kayıt bu alanı
  taşımıyor. Bu yüzden BTC ve ETH koşuları kayıttan ayırt edilemiyordu.
- Bazı kayıtlar `verdict: pending` kaldı ya da hiç verdict taşımıyor; hipotez kartları
  ise karara bağlanmış durumda. Kart ↔ registry tutarsızlığı ADR-0004 md.3 ihlalidir.

## `pairs` nereden geliyor — TAHMİN DEĞİL

Değer, freqtrade'in ürettiği backtest artefaktından (`user_data/backtest_results/*.zip`)
okunur: her koşunun gerçekten hangi çiftlerde işlem açtığı orada yazılıdır. Registry
kaydı ile artefakt, **strateji + tarih aralığı + zaman yakınlığı** üçlüsüyle eşleştirilir.
Eşleşme tekil değilse alan DOLDURULMAZ ve durum raporlanır — uydurma veri yazılmaz.

Artefakt dizini `.gitignore`'dadır; bu script yalnız artefaktın elde olduğu makinede
anlamlı çalışır. Artefakt yoksa `pairs` `null` kalır (bilinmiyor), yanlış değil.

## Kullanım

    python scripts/backfill_registry.py --check
    python scripts/backfill_registry.py --apply [--results-dir <yol>]
"""

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from registrylib import read_all, verify_encoding  # noqa: E402

REGISTRY = REPO / "registry" / "experiments.jsonl"
DEFAULT_RESULTS = REPO / "user_data" / "backtest_results"

# Hipotez kartlarının kararı (docs/hypotheses/*.md "Durum" satırı ile birebir).
CARD_VERDICTS = {
    "S-0001": (
        "rejected",
        "Yayın adayı değil (§1.3 kriter 1 sağlanmıyor); taban çizgisi olarak AKTİF kalır",
    ),
    "S-0002": None,  # zaten INVALID işaretli, dokunulmaz
    "S-0002b": ("rejected", "§1.3 kriter 1 başarısız: maliyet sonrası beklenti −17 bps"),
}


def artifact_index(results_dir: Path) -> list[dict]:
    """Backtest artefaktlarını (strateji, aralık, çiftler, bitiş zamanı) olarak listeler."""
    items = []
    for zpath in sorted(results_dir.glob("backtest-result-*.zip")):
        meta_path = Path(str(zpath)[:-4] + ".meta.json")
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        strategy = next(iter(meta), None)
        if strategy is None:
            continue
        with zipfile.ZipFile(zpath) as zf:
            inner = [n for n in zf.namelist() if n.endswith(".json") and "meta" not in n]
            if not inner:
                continue
            st = json.loads(zf.read(inner[0]))["strategy"][strategy]
        trades = st["trades"]
        items.append(
            {
                "file": zpath.name,
                "strategy": strategy,
                "start": st["backtest_start"][:10],
                "end": st["backtest_end"][:10],
                "pairs": sorted({t["pair"] for t in trades}),
                # Efektif fee, senaryo kimliğidir: registry `effective_fee` ile doğrulanır
                "fee": round(trades[0]["fee_open"], 8) if trades else None,
                "run_start_ts": meta[strategy].get("backtest_start_time"),
            }
        )
    return items


def _timerange_bounds(timerange: str | None) -> tuple[str, str] | None:
    """'20240101-20260203' → ('2024-01-01', '2026-02-03')."""
    if not timerange or "-" not in timerange:
        return None
    a, _, b = timerange.partition("-")
    if len(a) != 8 or len(b) != 8:
        return None
    return f"{a[:4]}-{a[4:6]}-{a[6:]}", f"{b[:4]}-{b[4:6]}-{b[6:]}"


def assign_pairs(
    rows: list[dict], artifacts: list[dict]
) -> dict[str, tuple[list[str] | None, str]]:
    """Her kayda çiftleri ata: grup içinde SIRALI birebir eşleme + fee doğrulaması.

    Neden en-yakın-zaman değil: registry kaydı koşu BİTİNCE yazılır, artefakt zaman
    damgası ise koşunun BAŞLANGICIDIR. Aradaki koşu süresi kadar sistematik kayma,
    "en yakın artefakt" yaklaşımını bir sonraki koşuya kaydırır (ilk denemede ETH
    artefaktı yanlışlıkla iki kayda birden atandı).

    Doğru yöntem: (strateji, tarih aralığı) grubunda kayıtları ve artefaktları zamana
    göre sırala, birebir eşle, sonra her eşleşmede `effective_fee == artefakt fee`
    kontrolüyle doğrula. Fee tutmuyorsa eşleşme reddedilir — sessizce yanlış çift
    yazmaktansa alan boş kalır.
    """
    out: dict[str, tuple[list[str] | None, str]] = {}
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        bounds = _timerange_bounds(r.get("timerange"))
        groups.setdefault((r.get("strategy"), bounds), []).append(r)

    for (strategy, bounds), entries in groups.items():
        cands = [a for a in artifacts if a["strategy"].startswith(strategy or "\0")]
        if bounds:
            cands = [a for a in cands if (a["start"], a["end"]) == bounds]
        if not cands:
            for r in entries:
                out[r["experiment_id"]] = (None, "eşleşen artefakt yok")
            continue

        # Tek tip çift varsa fee eşlemesine gerek yok
        if len({tuple(a["pairs"]) for a in cands}) == 1:
            for r in entries:
                out[r["experiment_id"]] = (cands[0]["pairs"], f"{len(cands)} artefakt, tek çift")
            continue

        if len(entries) != len(cands):
            for r in entries:
                out[r["experiment_id"]] = (
                    None,
                    f"belirsiz ({len(entries)} kayıt ↔ {len(cands)} artefakt)",
                )
            continue

        entries_sorted = sorted(entries, key=lambda r: r.get("created_at_utc") or "")
        cands_sorted = sorted(cands, key=lambda a: a["run_start_ts"] or 0)
        for r, a in zip(entries_sorted, cands_sorted, strict=True):
            fee = r.get("effective_fee")
            if fee is not None and a["fee"] is not None and abs(float(fee) - a["fee"]) > 1e-9:
                out[r["experiment_id"]] = (
                    None,
                    f"fee uyuşmuyor (kayıt {fee} ↔ artefakt {a['fee']})",
                )
            else:
                out[r["experiment_id"]] = (
                    a["pairs"],
                    f"sıralı eşleme + fee doğrulandı ({a['file']})",
                )
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    args = ap.parse_args()

    if verify_encoding(REGISTRY):
        sys.exit("HATA: registry UTF-8 değil; önce repair_registry_encoding.py --apply koş")

    rows = read_all()
    artifacts = artifact_index(args.results_dir) if args.results_dir.is_dir() else []
    print(f"{len(rows)} kayıt · {len(artifacts)} backtest artefaktı ({args.results_dir})")
    if not artifacts:
        print("UYARI: artefakt bulunamadı → pairs doldurulamaz (bilinmiyor olarak kalır)")

    assignments = assign_pairs(rows, artifacts) if artifacts else {}
    changes = []
    for r in rows:
        if not r.get("pairs") and assignments:
            pairs, why = assignments.get(r["experiment_id"], (None, "atanmadı"))
            if pairs:
                r["pairs"] = pairs
                changes.append((r["experiment_id"], "pairs", pairs, why))
            else:
                changes.append((r["experiment_id"], "pairs", "ATLANDI", why))

        current = str(r.get("verdict") or "")
        card = CARD_VERDICTS.get(r.get("hypothesis_id"))
        needs_verdict = current == "" or current.split()[0].lower() == "pending"
        if needs_verdict and card:
            r["verdict"] = card[0]
            r["verdict_reason"] = card[1]
            changes.append(
                (r["experiment_id"], "verdict", card[0], "hipotez kartıyla eşleştirildi")
            )

    for eid, field, value, why in changes:
        mark = "  " if value != "ATLANDI" else "! "
        print(f"{mark}{eid} · {field} ← {value}   [{why}]")

    if args.check:
        pending = sum(1 for r in read_all() if str(r.get("verdict") or "").startswith("pending"))
        missing = sum(1 for r in read_all() if not r.get("pairs"))
        print(f"\n--check: yazılmadı. Mevcut durum → pending={pending}, pairs eksik={missing}")
        sys.exit(0)

    backup = REGISTRY.with_suffix(REGISTRY.suffix + ".prebackfill.bak")
    shutil.copy2(REGISTRY, backup)
    with REGISTRY.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    after = read_all()
    pending = sum(1 for r in after if str(r.get("verdict") or "").startswith("pending"))
    no_verdict = sum(1 for r in after if not r.get("verdict"))
    no_pairs = sum(1 for r in after if not r.get("pairs"))
    print(f"\nYAZILDI ({len(changes)} değişiklik). Yedek: {backup.name}")
    print(f"Kalan: pending={pending}, verdict'siz={no_verdict}, pairs'siz={no_pairs}")


if __name__ == "__main__":
    main()
