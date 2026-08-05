import json
from pathlib import Path

import pytest

from scripts.statistical_gates_cli import evaluate_bundle, main
from scripts.walk_forward_lib import LockedOOSAccessError


def _registry(path: Path) -> Path:
    rows = []
    for index in range(2):
        rows.append(
            {
                "experiment_id": f"E-{index}",
                "hypothesis_id": f"S-{index + 3:04d}",
                "strategy_version": f"code-{index}",
                "dataset_snapshot": "dataset-1",
                "exit_code": 0,
                "result": {"ok": True},
                "verdict": "rejected",
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _bundle() -> dict:
    variant_metrics = {}
    for variant in ("window:minus", "window:plus"):
        variant_metrics[variant] = {"realistic": 0.09, "taker_heavy": 0.07}
    return {
        "metadata": {"scope": "development", "end_utc": "2026-08-04T00:00:00Z"},
        "observed_trial_id": "candidate",
        "trial_returns": {
            "candidate": [0.01, 0.02, -0.005, 0.015, 0.007, 0.012, -0.002, 0.009],
            "control": [0.001, -0.001, 0.002, -0.002, 0.001, -0.001, 0.002, -0.002],
        },
        "configuration_returns": {
            "candidate": [0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01],
            "control": [-0.01, 0.00, -0.01, 0.00, -0.01, 0.00, -0.01, 0.00],
        },
        "sensitivity": {
            "base_parameters": {"window": 30},
            "base_metrics": {"realistic": 0.10, "taker_heavy": 0.08},
            "variant_metrics": variant_metrics,
        },
        "ablation": {
            "full_returns": {
                "realistic": [0.03, 0.02, 0.01, 0.02],
                "taker_heavy": [0.02, 0.01, 0.005, 0.01],
            },
            "without_family_returns": {
                "funding": {
                    "realistic": [0.01, 0.01, 0.00, 0.01],
                    "taker_heavy": [0.01, 0.00, 0.00, 0.00],
                }
            },
        },
        "fragility": {
            "period_returns": {
                "early": {
                    "realistic": [0.01, 0.012, 0.009],
                    "taker_heavy": [0.008, 0.009, 0.007],
                },
                "middle": {
                    "realistic": [0.012, 0.013, 0.011],
                    "taker_heavy": [0.009, 0.010, 0.008],
                },
                "late": {
                    "realistic": [0.009, 0.010, 0.008],
                    "taker_heavy": [0.007, 0.008, 0.006],
                },
            },
            "venue_returns": {
                "binance": {
                    "realistic": [0.010, 0.011, 0.009],
                    "taker_heavy": [0.008, 0.009, 0.007],
                },
                "independent_venue": {
                    "realistic": [0.009, 0.010, 0.008],
                    "taker_heavy": [0.007, 0.008, 0.006],
                },
            },
        },
    }


def test_bundle_is_deterministic_and_does_not_write_registry(tmp_path: Path):
    registry = _registry(tmp_path / "experiments.jsonl")
    before = registry.read_bytes()
    outputs = {
        json.dumps(evaluate_bundle(_bundle(), registry_path=registry), sort_keys=True)
        for _ in range(100)
    }
    assert len(outputs) == 1
    assert registry.read_bytes() == before
    report = evaluate_bundle(_bundle(), registry_path=registry)
    assert report["schema_version"] == "phase2-statistical-gates/v2"
    assert report["reports"]["fragility"]["status"] == "passed"


def test_bundle_cannot_open_locked_oos(tmp_path: Path):
    bundle = _bundle()
    bundle["metadata"]["end_utc"] = "2026-08-04T01:00:00Z"
    with pytest.raises(LockedOOSAccessError):
        evaluate_bundle(bundle, registry_path=_registry(tmp_path / "experiments.jsonl"))


def test_cli_reports_invalid_bundle_without_registry_write(tmp_path: Path, capsys):
    registry = _registry(tmp_path / "experiments.jsonl")
    bundle_path = tmp_path / "bundle.json"
    bundle = _bundle()
    del bundle["sensitivity"]["variant_metrics"]["window:plus"]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    before = registry.read_bytes()
    assert main(["--input", str(bundle_path), "--registry", str(registry)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert registry.read_bytes() == before
