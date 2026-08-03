"""Experiment Registry v0 sözleşme testleri (kural 8)."""

import json
from pathlib import Path

import pytest

from registrylib import count_runs, record_run


def _run(tmp: Path, **over):
    base = dict(
        strategy="S0001EmaCross",
        hypothesis_id="S-0001",
        scenario="realistic",
        effective_fee=0.00085,
        exit_code=0,
    )
    base.update(over)
    return record_run(registry_path=tmp / "experiments.jsonl", **base)


def test_record_appends_valid_jsonl(tmp_path: Path):
    e1 = _run(tmp_path)
    e2 = _run(tmp_path, scenario="taker_heavy")
    lines = (tmp_path / "experiments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["experiment_id"] == e1["experiment_id"]
    assert parsed[1]["scenario"] == "taker_heavy"
    for entry in parsed:
        for field in (
            "experiment_id",
            "created_at_utc",
            "strategy_version",
            "dataset_snapshot",
            "hypothesis_id",
            "created_by",
        ):
            assert entry[field], field
    assert e1["experiment_id"] != e2["experiment_id"]


def test_missing_required_field_fails_loud(tmp_path: Path):
    with pytest.raises(ValueError, match="eksik alan"):
        record_run(registry_path=tmp_path / "x.jsonl", strategy="S0001")


def test_count_runs_family(tmp_path: Path):
    _run(tmp_path)
    _run(tmp_path)
    _run(tmp_path, hypothesis_id="S-0002")
    reg = tmp_path / "experiments.jsonl"
    assert count_runs("S-0001", registry_path=reg) == 2
    assert count_runs("S-0002", registry_path=reg) == 1
    assert count_runs("S-9999", registry_path=reg) == 0
