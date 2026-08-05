"""Veri yolu çözümlemesi ve manifest↔veri doğrulaması testleri.

Yakalamak istediği hata sınıfı: monorepo birleşmesinde manifest taşındı ama ham veri
taşınmadı; "manifest var, veri yok" durumu hiçbir yerde alarm üretmiyordu.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import datapaths  # noqa: E402
from datapaths import data_dir, market_data_root, user_dir, verify_manifest  # noqa: E402


def _write_manifest(tmp: Path, files: list[tuple[str, bytes]]) -> Path:
    entries = []
    for rel, blob in files:
        entries.append(
            {
                "file": rel,
                "sha256": hashlib.sha256(blob).hexdigest(),
                "rows": 1,
                "date_min_utc": "2024-01-01T00:00:00+00:00",
                "date_max_utc": "2024-01-02T00:00:00+00:00",
            }
        )
    doc = {"generated_at_utc": "2026-08-04T00:00:00+00:00", "files": entries}
    path = tmp / "MANIFEST-20260804.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _setup(tmp: Path, monkeypatch, present: list[tuple[str, bytes]], declared=None):
    """declared: manifestte ilan edilenler (verilmezse present ile aynı)."""
    userdir = tmp / "user_data"
    for rel, blob in present:
        target = userdir / Path(rel).relative_to("user_data")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    monkeypatch.setenv("RADAR_SIGNAL_USERDIR", str(userdir))
    monkeypatch.setattr(datapaths, "MANIFEST_DIR", tmp)
    return _write_manifest(tmp, declared if declared is not None else present)


F1 = ("user_data/data/binance/futures/A.feather", b"aaa")
F2 = ("user_data/data/binance/futures/B.feather", b"bbb")


def test_env_var_overrides_user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_SIGNAL_USERDIR", str(tmp_path / "baska"))
    assert user_dir() == tmp_path / "baska"
    assert market_data_root() == tmp_path / "baska" / "data"
    assert data_dir() == tmp_path / "baska" / "data" / "binance"


def test_default_user_dir_when_env_absent(monkeypatch):
    monkeypatch.delenv("RADAR_SIGNAL_USERDIR", raising=False)
    assert user_dir().name == "user_data"


def test_all_present_is_ok(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [F1, F2])
    assert verify_manifest()["status"] == "ok"


def test_partial_data_is_failure(tmp_path, monkeypatch):
    """ASIL YAKALANAN SINIF: manifest 2 dosya diyor, diskte 1 tane var."""
    _setup(tmp_path, monkeypatch, present=[F1], declared=[F1, F2])
    report = verify_manifest()
    assert report["status"] == "missing_data"
    assert report["missing"] == [F2[0]]


def test_no_data_at_all_is_distinct_from_partial(tmp_path, monkeypatch):
    """CI runner'ının normal hâli: hiç veri yok. 'missing_data' ile aynı sayılmamalı."""
    _setup(tmp_path, monkeypatch, present=[], declared=[F1, F2])
    report = verify_manifest()
    assert report["status"] == "no_data"
    assert len(report["missing"]) == 2


def test_hash_mismatch_is_failure(tmp_path, monkeypatch):
    """4 Ağu 2026: mark dosyaları manifest üretildikten sonra 1'er satır büyümüştü."""
    changed = (F1[0], b"degisti")
    _setup(tmp_path, monkeypatch, present=[changed, F2], declared=[F1, F2])
    report = verify_manifest()
    assert report["status"] == "hash_mismatch"
    assert report["mismatched"] == [F1[0]]


def test_missing_manifest_is_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_SIGNAL_USERDIR", str(tmp_path / "user_data"))
    monkeypatch.setattr(datapaths, "MANIFEST_DIR", tmp_path / "bos")
    (tmp_path / "bos").mkdir()
    assert verify_manifest()["status"] == "missing_manifest"


def test_real_repo_manifest_matches_reality_or_has_no_data():
    """Gerçek repo: veri varsa manifest tutmalı; hiç veri yoksa (CI) sorun değil."""
    report = verify_manifest()
    assert report["status"] in ("ok", "no_data", "missing_manifest"), (
        f"manifest gerçeği yansıtmıyor: {report}"
    )
