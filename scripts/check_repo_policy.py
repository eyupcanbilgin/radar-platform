"""Monorepoya secret/runtime verisi ve aşırı büyük dosya girişini engeller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent
MAX_TRACKED_BYTES = 50 * 1024 * 1024

FORBIDDEN_PARTS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
    "var",
    "backtest_results",
    "hyperopt_results",
}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12"}
FORBIDDEN_EXACT = {".claude/settings.local.json"}


def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in proc.stdout.split(b"\0") if item]


def violations(paths: list[str]) -> list[str]:
    failures: list[str] = []
    for raw in paths:
        path = PurePosixPath(raw)
        lowered = raw.lower()
        parts = {part.lower() for part in path.parts}

        if any(lowered.endswith(exact) for exact in FORBIDDEN_EXACT):
            failures.append(f"yerel ayar izleniyor: {raw}")
        if path.name == ".env" or (
            path.name.startswith(".env.") and path.name != ".env.example"
        ):
            failures.append(f"ortam dosyası izleniyor: {raw}")
        if parts & FORBIDDEN_PARTS:
            failures.append(f"çalışma zamanı yolu izleniyor: {raw}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"secret/veritabanı uzantısı izleniyor: {raw}")
        if "user_data" in parts and "data" in parts:
            failures.append(f"ham piyasa verisi izleniyor: {raw}")

        local = REPO / Path(*path.parts)
        if local.is_file() and local.stat().st_size > MAX_TRACKED_BYTES:
            failures.append(f"50 MiB üzeri dosya izleniyor: {raw}")
    return sorted(set(failures))


def main() -> int:
    failures = violations(tracked_files())
    if failures:
        print("Repository policy ihlalleri:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Repository policy: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
