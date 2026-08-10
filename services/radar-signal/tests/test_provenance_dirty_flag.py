"""Fully synthetic tests for the clean-tree provenance guard.

Each test builds its own throwaway git repository in ``tmp_path``; none of them read the
real working tree, ``user_data/`` or the live registry.

Why this file exists: on 2026-08-10 every recorded measurement — S-0003, S-0004 and all
three S-0005 runs — carried ``git_dirty: true``.  The cause was not a dirty checkout but the
guard counting the run's own append-only Registry write as dirt, which made the flag
impossible to satisfy and therefore worthless as the gate ADR-0003 / Platform ADR-0004 /
CLAUDE.md rule 13 rely on.
"""

import subprocess
from pathlib import Path

import pytest

from scripts import provenance


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A committed, clean throwaway repo with a source file and an evidence log."""
    root = tmp_path / "repo"
    (root / "registry").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "strategy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "registry" / "experiments.jsonl").write_text('{"experiment_id":"E-1"}\n', "utf-8")
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "seed")
    monkeypatch.setattr(provenance, "REPO", root)
    return root


def test_clean_tree_is_not_dirty(repo: Path):
    assert provenance.git_is_dirty() is False


def test_appending_to_the_evidence_log_is_not_dirt(repo: Path):
    """Bu, düzeltilen kusurun ta kendisi: her ölçüm Registry'ye yazar.

    Bunu kirlilik saymak, bayrağın hiçbir gerçek koşuda False olamamasına ve dolayısıyla
    hiçbir şeyi korumamasına yol açıyordu.
    """
    log = repo / "registry" / "experiments.jsonl"
    log.write_text(log.read_text(encoding="utf-8") + '{"experiment_id":"E-2"}\n', "utf-8")

    assert provenance.git_is_dirty() is False
    # Ham git davranışı hâlâ kirli der; fark bilinçlidir, gizlenmiş bir hata değildir.
    assert provenance.git_is_dirty(ignore=()) is True


def test_verdict_event_log_is_also_expected_output(repo: Path):
    (repo / "registry" / "verdict_events.jsonl").write_text('{"event_id":"V-1"}\n', "utf-8")
    assert provenance.git_is_dirty() is False


def test_modified_source_is_still_dirty(repo: Path):
    """Muafiyet yalnız kanıt kütüklerinedir; koruma asıl işini yapmaya devam eder."""
    (repo / "scripts" / "strategy.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert provenance.git_is_dirty() is True


def test_untracked_source_file_is_still_dirty(repo: Path):
    (repo / "scripts" / "sneaky.py").write_text("VALUE = 3\n", encoding="utf-8")
    assert provenance.git_is_dirty() is True


def test_evidence_log_plus_modified_source_is_dirty(repo: Path):
    """Kanıt kütüğü muafiyeti, yanındaki gerçek kirliliği maskelemez."""
    log = repo / "registry" / "experiments.jsonl"
    log.write_text(log.read_text(encoding="utf-8") + '{"experiment_id":"E-3"}\n', "utf-8")
    (repo / "scripts" / "strategy.py").write_text("VALUE = 9\n", encoding="utf-8")
    assert provenance.git_is_dirty() is True


def test_renamed_source_is_dirty(repo: Path):
    _git(repo, "mv", "scripts/strategy.py", "scripts/renamed.py")
    assert provenance.git_is_dirty() is True


def test_lookalike_directory_cannot_borrow_the_exemption(repo: Path):
    """Muafiyet dizin sınırına saygı gösterir.

    Düz `endswith` ile `evil-registry/experiments.jsonl` de muaf olurdu; muafiyet o zaman
    korumadan kaçmak için kullanılabilecek bir açığa dönerdi.
    """
    sneaky = repo / "evil-registry"
    sneaky.mkdir()
    (sneaky / "experiments.jsonl").write_text('{"experiment_id":"E-9"}\n', encoding="utf-8")
    assert provenance.git_is_dirty() is True
