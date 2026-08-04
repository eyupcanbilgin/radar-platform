import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from run_pulse_reanalysis import (
    PLATFORM_ROOT,
    is_git_ancestor,
    readiness_errors,
    review_attestation_errors,
    validate_development_window,
    verify_reviewed_files,
)


def get_real_scoped_files_and_hashes() -> tuple[list[str], dict[str, str]]:
    rel_path = "services/radar-signal/scripts/signal_pulse.py"
    full_path = PLATFORM_ROOT / rel_path
    file_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
    scope = [rel_path]
    files = {rel_path: file_hash}
    return scope, files


def test_development_window_allows_end_exclusive_locked_boundary():
    validate_development_window("2024-01-01", "2026-08-04")


def test_development_window_refuses_locked_oos_data():
    with pytest.raises(ValueError, match="locked OOS ihlali"):
        validate_development_window("2024-01-01", "2026-08-05")


def test_official_reanalysis_refuses_dirty_tree(tmp_path: Path):
    errors = readiness_errors(
        output=tmp_path / "report.json",
        allow_dirty_smoke=False,
        dirty=True,
        manifest_report={"status": "ok"},
    )
    assert any("dirty" in error for error in errors)


def test_dirty_smoke_must_stay_under_service_var():
    errors = readiness_errors(
        output=Path("outside.json"),
        allow_dirty_smoke=True,
        dirty=True,
        manifest_report={"status": "ok"},
    )
    assert any("var altında" in error for error in errors)


def test_manifest_must_match_data(tmp_path: Path):
    errors = readiness_errors(
        output=tmp_path / "report.json",
        allow_dirty_smoke=False,
        dirty=False,
        manifest_report={"status": "hash_mismatch"},
    )
    assert errors == ["dataset manifest hazır değil: hash_mismatch"]


def test_official_reanalysis_requires_review_attestation(tmp_path: Path):
    errors = review_attestation_errors(tmp_path / "missing.json", "abc123456789")
    assert len(errors) == 1
    assert "bağımsız inceleme kaydı yok" in errors[0]


def test_schema_v1_is_rejected(tmp_path: Path):
    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "reviewed_commit": "abc123456789",
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    errors = review_attestation_errors(attestation, "abc123456789")
    assert any("v1 şeması desteklenmiyor" in error for error in errors)


def test_valid_schema_v2_review_attestation_passes(tmp_path: Path):
    current_head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()[:12]

    scope, files = get_real_scoped_files_and_hashes()

    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "reviewed_commit": current_head,
                "review_scope": scope,
                "reviewed_files": files,
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    assert review_attestation_errors(attestation, current_head) == []


def test_bootstrap_paradox_resolved_when_reviewed_commit_is_ancestor_of_head(tmp_path: Path):
    # Retrieve the parent commit of current HEAD
    parent_commit = (
        subprocess.run(
            ["git", "log", "-2", "--format=%H"],
            cwd=PLATFORM_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .splitlines()[-1][:12]
    )

    current_head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()[:12]

    assert parent_commit != current_head
    assert is_git_ancestor(parent_commit, current_head) is True

    scope, files = get_real_scoped_files_and_hashes()

    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "reviewed_commit": parent_commit,
                "review_scope": scope,
                "reviewed_files": files,
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    # Under schema v2, attestation committed in HEAD referencing parent commit passes!
    assert review_attestation_errors(attestation, current_head) == []


def test_non_ancestor_commit_is_rejected(tmp_path: Path):
    current_head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()[:12]

    scope, files = get_real_scoped_files_and_hashes()

    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "reviewed_commit": "boguscommit12",
                "review_scope": scope,
                "reviewed_files": files,
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    errors = review_attestation_errors(attestation, current_head)
    assert any("geçerli signal commit'inin atası değil" in error for error in errors)


def test_modified_scoped_file_is_rejected(tmp_path: Path):
    current_head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()[:12]

    scope, files = get_real_scoped_files_and_hashes()
    tampered_files = dict(files)
    tampered_files[scope[0]] = "f" * 64

    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "reviewed_commit": current_head,
                "review_scope": scope,
                "reviewed_files": tampered_files,
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    errors = review_attestation_errors(attestation, current_head)
    assert any("incelenen dosya içeriği değişmiş" in error for error in errors)


def test_missing_scoped_file_is_rejected(tmp_path: Path):
    current_head = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()[:12]

    scope = ["services/radar-signal/non_existent_file.py"]
    files = {"services/radar-signal/non_existent_file.py": "a" * 64}

    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "2",
                "reviewed_commit": current_head,
                "review_scope": scope,
                "reviewed_files": files,
                "reviewer": "independent-reviewer",
                "reviewed_at_utc": "2026-08-04T12:00:00Z",
                "verdict": "approved",
                "independent": True,
                "checks": {
                    "statistics": True,
                    "locked_oos": True,
                    "registry": True,
                    "reporting": True,
                },
            }
        ),
        encoding="utf-8",
    )

    errors = review_attestation_errors(attestation, current_head)
    assert any("incelenen dosya bulunamadı" in error for error in errors)


def test_mismatched_scope_and_files_rejected(tmp_path: Path):
    errors = verify_reviewed_files(
        reviewed_files={"fileA.py": "a" * 64},
        review_scope=["fileB.py"],
    )
    assert any("dosya listeleri uyuşmuyor" in error for error in errors)


def test_dirty_smoke_ignores_review_gate(tmp_path: Path):
    errors = readiness_errors(
        output=Path(__file__).parents[1] / "var" / "smoke.json",
        allow_dirty_smoke=True,
        dirty=True,
        manifest_report={"status": "ok"},
        review_errors=["missing review"],
    )
    assert errors == []
