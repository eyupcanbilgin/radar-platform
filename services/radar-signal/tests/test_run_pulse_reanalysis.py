import json
from pathlib import Path

import pytest
from run_pulse_reanalysis import (
    readiness_errors,
    review_attestation_errors,
    validate_development_window,
)


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


def test_review_attestation_must_match_current_signal_commit(tmp_path: Path):
    attestation = tmp_path / "review.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "reviewed_commit": "old123456789",
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

    errors = review_attestation_errors(attestation, "new123456789")
    assert any("geçerli signal commit'ine bağlı değil" in error for error in errors)


def test_valid_review_attestation_passes(tmp_path: Path):
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

    assert review_attestation_errors(attestation, "abc123456789") == []


def test_dirty_smoke_ignores_review_gate(tmp_path: Path):
    errors = readiness_errors(
        output=Path(__file__).parents[1] / "var" / "smoke.json",
        allow_dirty_smoke=True,
        dirty=True,
        manifest_report={"status": "ok"},
        review_errors=["missing review"],
    )
    assert errors == []
