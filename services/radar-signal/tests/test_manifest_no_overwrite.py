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
