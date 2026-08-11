"""Fully synthetic tests: an existing manifest is immutable evidence, never overwritten.

Why: Registry rows point at a manifest via ``dataset_snapshot``.  Regenerating the manifest
on the same UTC day used to reuse the same filename, so adding one data file silently
replaced the snapshot that earlier runs depend on.  On 2026-08-10 four recorded runs
(S-0005 ×3, S-0006) referenced ``637104fb…`` and a same-day regeneration would have
overwritten exactly that file.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import data_manifest


@pytest.fixture
def out_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(data_manifest, "OUT_DIR", tmp_path)
    return tmp_path


NOW = datetime(2026, 8, 10, 21, 5, 30, tzinfo=UTC)


def _write(path: Path, digest: str) -> None:
    path.write_text(json.dumps({"manifest_sha256": digest}), encoding="utf-8")


def test_first_manifest_of_the_day_uses_the_plain_date_name(out_dir: Path):
    target = data_manifest._manifest_target(NOW, "aaaa")
    assert target.name == "MANIFEST-20260810.json"


def test_identical_content_reuses_the_same_path(out_dir: Path):
    _write(out_dir / "MANIFEST-20260810.json", "aaaa")
    target = data_manifest._manifest_target(NOW, "aaaa")
    assert target.name == "MANIFEST-20260810.json"


def test_different_content_never_overwrites_the_existing_snapshot(out_dir: Path):
    existing = out_dir / "MANIFEST-20260810.json"
    _write(existing, "637104fb")

    target = data_manifest._manifest_target(NOW, "22b52c28")

    assert target.name == "MANIFEST-20260810T210530.json"
    # Eski snapshot yerinde ve bozulmamış olmalı: dört registry satırı ona işaret ediyor.
    assert json.loads(existing.read_text(encoding="utf-8"))["manifest_sha256"] == "637104fb"


def test_timestamped_manifest_still_sorts_as_the_newest(out_dir: Path):
    """`latest_manifest_path()` glob'u sıralayıp sonuncuyu alır; sıra bozulmamalı."""
    _write(out_dir / "MANIFEST-20260810.json", "eski")
    _write(out_dir / "MANIFEST-20260810T210530.json", "yeni")

    newest = sorted(out_dir.glob("MANIFEST-*.json"))[-1]
    assert newest.name == "MANIFEST-20260810T210530.json"


def test_next_day_manifest_sorts_after_a_timestamped_one(out_dir: Path):
    _write(out_dir / "MANIFEST-20260810T210530.json", "dun")
    _write(out_dir / "MANIFEST-20260811.json", "bugun")

    newest = sorted(out_dir.glob("MANIFEST-*.json"))[-1]
    assert newest.name == "MANIFEST-20260811.json"


def test_unreadable_existing_manifest_is_not_overwritten(out_dir: Path):
    """Okunamayan manifest 'içerik aynı' sayılmaz; sessizce üzerine yazılmaz."""
    broken = out_dir / "MANIFEST-20260810.json"
    broken.write_text("{ bozuk", encoding="utf-8")

    target = data_manifest._manifest_target(NOW, "aaaa")

    assert target.name == "MANIFEST-20260810T210530.json"
    assert broken.read_text(encoding="utf-8") == "{ bozuk"


# --- Zaman kolonu: on-chain seriler `date` taşımaz ve taşımamalıdır --------------------


@pytest.fixture
def repo_root(tmp_path: Path, monkeypatch) -> Path:
    """`file_entry` yolu depo köküne göreli yazar; geçici dizin kök sayılır."""
    monkeypatch.setattr(data_manifest, "REPO", tmp_path)
    return tmp_path


def _feather(path: Path, frame) -> Path:
    frame.to_feather(path)
    return path


def test_ohlcv_files_keep_using_their_date_column(repo_root: Path):
    import pandas as pd

    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-08-01", "2026-08-02"], utc=True), "close": [1.0, 2.0]}
    )
    entry = data_manifest.file_entry(_feather(repo_root / "ohlcv.feather", frame))

    assert entry["time_column"] == "date"
    assert entry["date_min_utc"].startswith("2026-08-01")


def test_an_onchain_series_is_indexed_by_its_event_time_not_its_availability(repo_root: Path):
    """`available_at_utc` kullanılsaydı manifest aralığı veriyi olduğundan yeni gösterirdi."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "day": ["2026-08-01"],
            "event_time_utc": pd.to_datetime(["2026-08-02"], utc=True),
            "available_at_utc": pd.to_datetime(["2026-08-03"], utc=True),
            "sthSopr": [1.0],
        }
    )
    entry = data_manifest.file_entry(_feather(repo_root / "sopr.feather", frame))

    assert entry["time_column"] == "event_time_utc"
    assert entry["date_max_utc"].startswith("2026-08-02")


def test_a_file_without_any_known_time_column_fails_loudly(repo_root: Path):
    import pandas as pd

    frame = pd.DataFrame({"value": [1.0]})

    with pytest.raises(ValueError, match="zaman kolonu yok"):
        data_manifest.file_entry(_feather(repo_root / "bilinmeyen.feather", frame))
