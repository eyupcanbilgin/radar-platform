"""Replay determinizmi (DoD) + ortam parmak izi (onay ŞART A)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from provenance import environment_fingerprint, lockfile_hash  # noqa: E402
from replay import DEFAULT_EVENTS, load_events, run_once  # noqa: E402

from enricher.policy import load_lifecycle  # noqa: E402


def test_lockfile_hash_is_stable_and_recorded():
    """ŞART A: bağımlılık kilidi parmak izinin parçasıdır."""
    assert lockfile_hash() == lockfile_hash()
    assert len(lockfile_hash()) == 64
    fp = environment_fingerprint()
    assert fp["lockfile_sha256"] == lockfile_hash()


def test_fingerprint_has_all_provenance_fields():
    fp = environment_fingerprint()
    for key in (
        "git_commit",
        "git_dirty",
        "lockfile_sha256",
        "costs_sha256",
        "lifecycle_sha256",
        "dataset_snapshot",
    ):
        assert key in fp, key
    assert isinstance(fp["git_dirty"], bool)


def test_replay_is_bit_identical_100x():
    """KABUL: aynı olay seti + aynı ortam → 100 turda tek çıktı hash'i."""
    events = load_events(DEFAULT_EVENTS)
    lifecycle = load_lifecycle()
    digests = {run_once(events, lifecycle) for _ in range(100)}
    assert len(digests) == 1, f"determinizm bozuldu: {len(digests)} farklı çıktı"


def test_replay_fixture_exercises_all_gate_paths():
    """Fixture yalnız mutlu yolu değil BLOCK ve degraded yollarını da kapsamalı."""
    events = load_events(DEFAULT_EVENTS)
    raw = json.loads(DEFAULT_EVENTS.read_text(encoding="utf-8"))
    assert any(e.get("blackout_reason") for e in raw), "karartma senaryosu eksik"
    assert any(not e["inputs_available"]["atr"] for e in raw), "zorunlu-eksik senaryosu eksik"
    assert any(not e["inputs_available"]["regime"] for e in raw), "degraded senaryosu eksik"
    assert len({e.asset for e in events}) > 1, "tek varlık — çok varlıklı sıra test edilmiyor"


def test_changed_event_changes_digest():
    """Determinizm testi 'her zaman aynı' demek değil; girdi değişince çıktı değişmeli."""
    events = load_events(DEFAULT_EVENTS)
    lifecycle = load_lifecycle()
    base = run_once(events, lifecycle)
    events[0].entry_reference = 99999.0
    assert run_once(events, lifecycle) != base


def test_lockfile_missing_fails_loud(monkeypatch):
    import provenance

    monkeypatch.setattr(provenance, "LOCKFILE", REPO / "yok-boyle-bir-dosya.lock")
    with pytest.raises(FileNotFoundError, match="parmak izi"):
        provenance.lockfile_hash()
