"""GERÇEK registry dosyasının bütünlük testleri.

Diğer registry testleri `tmp_path` üzerinde sentetik dosyayla çalışır — bu yüzden
4 Ağu 2026'daki gerçek arızayı (7 satırın cp1254 ile yazılması) hiçbiri yakalamadı.
Bu dosya bilerek `registry/experiments.jsonl`'ın KENDİSİNİ okur: bozulma tekrarlarsa
CI kırmızı olur.

Testler artefakt/veri gerektirmez, saniyeler sürer ve yalnız repodaki dosyaya bakar.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from registrylib import (  # noqa: E402
    REGISTRY_PATH,
    VALID_CREATORS,
    VALID_VERDICTS,
    VERDICT_EVENTS_PATH,
    RegistryEncodingError,
    read_all,
    read_verdict_events,
    verify_encoding,
)


@pytest.fixture(scope="module")
def raw_lines() -> list[bytes]:
    if not REGISTRY_PATH.exists():
        pytest.skip("registry dosyası yok")
    return [ln for ln in REGISTRY_PATH.read_bytes().splitlines() if ln.strip()]


def test_registry_is_valid_utf8():
    """REGRESYON: 4 Ağu 2026 — 7 satır Windows ANSI (cp1254) ile yazılmıştı."""
    bad = verify_encoding()
    assert bad == [], (
        f"registry'de UTF-8 olmayan satır(lar): {bad}. "
        "Onarım: python scripts/repair_registry_encoding.py --apply"
    )


def test_registry_has_no_bom_and_no_crlf(raw_lines):
    """BOM ve CRLF de JSONL bütünlüğünü bozar; encoding kadar sinsi."""
    blob = REGISTRY_PATH.read_bytes()
    assert not blob.startswith(b"\xef\xbb\xbf"), "dosya BOM ile başlıyor"
    assert b"\r\n" not in blob, "dosyada CRLF satır sonu var (newline='\\n' bekleniyor)"


def test_every_line_is_valid_json(raw_lines):
    for i, ln in enumerate(raw_lines, 1):
        try:
            json.loads(ln.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            pytest.fail(f"satır {i} okunamadı: {exc}")


def test_read_all_works_on_real_file():
    """Kütüphanenin kendi dosyasını okuyabildiğini doğrular (arıza tam buradaydı)."""
    rows = read_all()
    assert rows, "registry boş"
    assert all("experiment_id" in r for r in rows)


def test_verdict_event_file_is_valid_and_targets_known_experiments():
    assert VERDICT_EVENTS_PATH.exists(), "append-only verdict event kütüğü yok"
    assert verify_encoding(VERDICT_EVENTS_PATH) == []
    known_ids = {row["experiment_id"] for row in read_all()}
    events = read_verdict_events()
    assert events, "en az S-0002b kanıt düzeltmesi bekleniyor"
    assert all(event["experiment_id"] in known_ids for event in events)
    assert len({event["event_id"] for event in events}) == len(events)


def test_experiment_ids_are_unique():
    ids = [r["experiment_id"] for r in read_all()]
    assert len(ids) == len(set(ids)), "yinelenen experiment_id var"


def test_required_fields_present_on_every_record():
    for r in read_all():
        for field in ("hypothesis_id", "strategy", "scenario", "effective_fee", "created_at_utc"):
            assert r.get(field) is not None, f"{r['experiment_id']}: '{field}' eksik"


def test_verdicts_are_valid_and_closed():
    """Kapanmamış (`pending`) koşu kalmamalı — ADR-0004 md.3."""
    for r in read_all():
        verdict = str(r.get("verdict") or "")
        assert verdict, f"{r['experiment_id']}: verdict yok"
        base = verdict.split()[0].lower()
        assert base in VALID_VERDICTS, f"{r['experiment_id']}: geçersiz verdict {verdict!r}"
        assert base != "pending", (
            f"{r['experiment_id']} hâlâ 'pending' — hipotez kartıyla eşleştirilmeli"
        )


def test_s0002b_runs_are_effectively_invalid_after_audit():
    rows = [row for row in read_all() if row.get("hypothesis_id") == "S-0002b"]
    assert len(rows) == 3
    assert all(row["verdict"] == "invalid" for row in rows)
    assert all(row.get("initial_verdict") == "rejected" for row in rows)


def test_created_by_is_known():
    for r in read_all():
        by = r.get("created_by")
        if by is not None:  # şema v1 kayıtlarında alan yok
            assert by in VALID_CREATORS, f"{r['experiment_id']}: bilinmeyen created_by {by!r}"


def test_pairs_filled_where_known():
    """`pairs` boş kalabilir (bilinmiyor) ama dolu olan her değer liste olmalı."""
    for r in read_all():
        pairs = r.get("pairs")
        if pairs is not None:
            assert isinstance(pairs, list) and pairs, f"{r['experiment_id']}: pairs bozuk {pairs!r}"
            assert all(isinstance(p, str) for p in pairs)


# --- Dedektörün kendisi çalışıyor mu? ---------------------------------------------------
# Yukarıdaki testler "dosya temiz" der. Aşağıdakiler "kirli olsaydı yakalardık" der.
# İkisi birlikte olmadan yeşil test, çalışmayan bir dedektörü de gizleyebilirdi.

CORRUPT_LINE = '{"experiment_id": "E-TEST", "verdict": "INVALID — ölçüm hatası"}'


def test_detector_catches_cp1254_bytes(tmp_path):
    """4 Ağu 2026 arızasının birebir kopyası: aynı satır cp1254 ile yazılırsa yakalanmalı."""
    path = tmp_path / "experiments.jsonl"
    path.write_bytes(CORRUPT_LINE.encode("cp1254") + b"\n")
    assert verify_encoding(path) == [1]
    with pytest.raises(RegistryEncodingError, match="UTF-8 değil"):
        read_all(path)


def test_detector_passes_same_line_in_utf8(tmp_path):
    path = tmp_path / "experiments.jsonl"
    path.write_bytes(CORRUPT_LINE.encode("utf-8") + b"\n")
    assert verify_encoding(path) == []
    assert read_all(path)[0]["experiment_id"] == "E-TEST"


def test_read_all_never_falls_back_silently(tmp_path):
    """Sessiz kod sayfası fallback'i yasak: bozuk kayıt yanlış çözülerek okunmamalı."""
    path = tmp_path / "experiments.jsonl"
    path.write_bytes(CORRUPT_LINE.encode("cp1254") + b"\n")
    with pytest.raises(RegistryEncodingError):
        read_all(path)
