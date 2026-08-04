"""Run pulse-v2 only behind clean-tree, manifest and locked-OOS safety gates."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from datapaths import verify_manifest  # noqa: E402
from generate_report import build_report  # noqa: E402
from provenance import git_commit  # noqa: E402
from signal_pulse import run_workbench, write_json_report  # noqa: E402

LOCKED_OOS_START = date(2026, 8, 4)
PLATFORM_ROOT = SERVICE_ROOT.parent.parent
REVIEW_ATTESTATION = (
    PLATFORM_ROOT / "docs" / "reviews" / "2026-08-04-wp0001" / "pulse-v2-review.json"
)
REQUIRED_REVIEW_CHECKS = {"statistics", "locked_oos", "registry", "reporting"}
DEFAULT_OUTPUT = (
    SERVICE_ROOT / "docs" / "reviews" / "2026-08-04-eleme-v2-development" / "pulse-v2-results.json"
)


def repository_is_dirty() -> bool:
    """Return whether any tracked or untracked path in the platform repo is dirty."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=PLATFORM_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(out.stdout.strip())


def is_git_ancestor(ancestor_commit: str, target_commit: str) -> bool:
    """Check if ancestor_commit is an ancestor of or equal to target_commit in git history."""
    if not isinstance(ancestor_commit, str) or not ancestor_commit.strip():
        return False
    if not isinstance(target_commit, str) or not target_commit.strip():
        return False
    try:
        res = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor_commit, target_commit],
            cwd=PLATFORM_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def verify_reviewed_files(reviewed_files: object, review_scope: object) -> list[str]:
    """Verify that all reviewed files exist and match their expected SHA-256 hashes."""
    if not isinstance(review_scope, list) or not review_scope:
        return ["inceleme kaydında review_scope boş olamaz ve liste olmalı"]
    if not isinstance(reviewed_files, dict) or not reviewed_files:
        return ["inceleme kaydında reviewed_files boş olamaz ve nesne olmalı"]

    scope_set = set(review_scope)
    files_set = set(reviewed_files.keys())
    if scope_set != files_set:
        return ["review_scope ve reviewed_files dosya listeleri uyuşmuyor"]

    errors: list[str] = []
    for rel_path in sorted(scope_set):
        expected_hash = reviewed_files[rel_path]
        if not isinstance(rel_path, str) or not rel_path.strip():
            errors.append("review_scope içinde geçersiz dosya yolu")
            continue
        if not isinstance(expected_hash, str) or not expected_hash.strip():
            errors.append(f"reviewed_files içinde {rel_path} için hash eksik")
            continue
        file_path = PLATFORM_ROOT / rel_path
        if not file_path.is_file():
            errors.append(f"incelenen dosya bulunamadı: {rel_path}")
            continue

        try:
            current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if current_hash != expected_hash:
                errors.append(
                    f"incelenen dosya içeriği değişmiş: {rel_path} "
                    f"(beklenen={expected_hash[:12]}, mevcut={current_hash[:12]})"
                )
        except OSError as exc:
            errors.append(f"incelenen dosya okunamadı: {rel_path} ({exc})")

    return errors


def review_attestation_errors(attestation_path: Path, current_commit: str) -> list[str]:
    """Validate the independent-review record bound to the signal code commit (schema v2)."""
    if not attestation_path.is_file():
        return [f"bağımsız inceleme kaydı yok: {attestation_path}"]

    try:
        record = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"bağımsız inceleme kaydı okunamadı: {exc}"]

    if not isinstance(record, dict):
        return ["bağımsız inceleme kaydı JSON nesnesi olmalı"]

    errors: list[str] = []
    schema_ver = str(record.get("schema_version", ""))
    if schema_ver != "2":
        return ["inceleme schema_version değeri '2' olmalı; v1 şeması desteklenmiyor"]

    reviewed_commit = record.get("reviewed_commit")
    if not isinstance(reviewed_commit, str) or not reviewed_commit.strip():
        errors.append("inceleme kaydında reviewed_commit zorunlu")
    elif not is_git_ancestor(reviewed_commit, current_commit):
        errors.append(
            "inceleme kaydı geçerli signal commit'inin atası değil: "
            f"current={current_commit}, kayıt={reviewed_commit}"
        )

    file_errors = verify_reviewed_files(
        reviewed_files=record.get("reviewed_files"),
        review_scope=record.get("review_scope"),
    )
    errors.extend(file_errors)

    if record.get("verdict") != "approved":
        errors.append("bağımsız inceleme verdict değeri 'approved' olmalı")
    if record.get("independent") is not True:
        errors.append("inceleme kaydı independent=true olmalı")
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        errors.append("inceleme kaydında reviewer zorunlu")
    if not isinstance(record.get("reviewed_at_utc"), str) or not record["reviewed_at_utc"].strip():
        errors.append("inceleme kaydında reviewed_at_utc zorunlu")

    checks = record.get("checks")
    if not isinstance(checks, dict):
        errors.append("inceleme kaydında checks nesnesi zorunlu")
    else:
        missing = sorted(check for check in REQUIRED_REVIEW_CHECKS if checks.get(check) is not True)
        if missing:
            errors.append("inceleme kontrolleri eksik/onaysız: " + ", ".join(missing))
    return errors


def validate_development_window(start: str, end: str) -> None:
    """Validate an end-exclusive Development window without touching locked OOS."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date >= end_date:
        raise ValueError("başlangıç tarihi bitişten önce olmalı")
    if end_date > LOCKED_OOS_START:
        raise ValueError(
            f"locked OOS ihlali: end={end} en fazla {LOCKED_OOS_START.isoformat()} olabilir "
            "(end exclusive)"
        )


def readiness_errors(
    *,
    output: Path,
    allow_dirty_smoke: bool,
    dirty: bool,
    manifest_report: dict,
    review_errors: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if manifest_report.get("status") != "ok":
        errors.append(f"dataset manifest hazır değil: {manifest_report.get('status')}")
    if dirty and not allow_dirty_smoke:
        errors.append("çalışma ağacı dirty; Development reanalysis temiz commit ister")
    if not allow_dirty_smoke and review_errors:
        errors.extend(review_errors)
    if allow_dirty_smoke:
        var_root = (SERVICE_ROOT / "var").resolve()
        if not output.resolve().is_relative_to(var_root):
            errors.append("dirty smoke çıktısı yalnız services/radar-signal/var altında olabilir")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-08-04", help="exclusive end")
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-dirty-smoke", action="store_true")
    args = parser.parse_args()

    validate_development_window(args.start, args.end)
    review_errors = []
    if not args.allow_dirty_smoke:
        review_errors = review_attestation_errors(REVIEW_ATTESTATION, git_commit())
    errors = readiness_errors(
        output=args.out,
        allow_dirty_smoke=args.allow_dirty_smoke,
        dirty=repository_is_dirty(),
        manifest_report=verify_manifest(),
        review_errors=review_errors,
    )
    if errors:
        raise SystemExit("Reanalysis kapısı kapalı:\n- " + "\n- ".join(errors))

    report = run_workbench(args.start, args.end, args.permutations, args.seed)
    digest = write_json_report(report, args.out)
    markdown_path = args.out.with_suffix(".md")
    markdown_path.write_text(build_report(report), encoding="utf-8")
    run_label = "Dirty smoke" if args.allow_dirty_smoke else "Development reanalysis"
    print(
        f"{run_label} tamamlandı: {args.out} · "
        f"tests={report['valid_tests']}/{report['total_registered_tests']} · "
        f"sha256={digest}"
    )


if __name__ == "__main__":
    main()
