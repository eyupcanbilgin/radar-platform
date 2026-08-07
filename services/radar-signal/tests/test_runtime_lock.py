from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-runtime.lock"
FORBIDDEN_RESEARCH_PACKAGES = {"freqtrade", "numpy", "pandas", "pyarrow"}


def _locked_names() -> set[str]:
    return {
        line.split("==", 1)[0].lower().replace("_", "-")
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }


def test_runtime_lock_has_required_direct_dependencies() -> None:
    assert {"ccxt", "httpx", "jsonschema", "pydantic", "pyyaml"} <= _locked_names()


def test_runtime_lock_excludes_research_packages() -> None:
    assert not FORBIDDEN_RESEARCH_PACKAGES & _locked_names()
