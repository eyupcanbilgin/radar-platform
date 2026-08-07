"""Keep the live context-set loader independent from research dataframe dependencies."""

import ast
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_live_loader_does_not_import_research_or_dataframe_modules():
    imports = _imports(SERVICE_ROOT / "decision_engine/context_sets.py")
    assert "pandas" not in imports
    assert "scripts.run_f0001_evidence" not in imports


def test_hourly_runtime_uses_the_lightweight_loader_directly():
    imports = _imports(SERVICE_ROOT / "scripts/run_hourly_decision.py")
    assert "decision_engine.context_sets" in imports
    assert "scripts.run_f0001_evidence" not in imports


def test_readiness_does_not_import_the_research_runner():
    imports = _imports(SERVICE_ROOT / "scripts/f0001_readiness.py")
    assert "decision_engine.context_sets" in imports
    assert "decision_engine.jsonio" in imports
    assert "scripts.run_f0001_evidence" not in imports
