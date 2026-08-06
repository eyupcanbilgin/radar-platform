import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from btc_radar.core.config import load_f0001_locked_oos, load_signal_rules
from btc_radar.core.research_contexts import generate_f0001_context_sets
from btc_radar.core.store import PointInTimeStore


def test_generates_three_sealed_directionless_context_sets_idempotently(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    output = tmp_path / "contexts"
    snapshots = tmp_path / "snapshots"
    with PointInTimeStore(tmp_path / "pit.sqlite") as pit:
        first = generate_f0001_context_sets(
            start_utc=start,
            end_exclusive_utc=end,
            locked_oos_start_utc=end,
            pit_store=pit,
            snapshot_root=snapshots,
            output_root=output,
            rules=load_signal_rules(),
        )
        before = {path: path.read_bytes() for path in output.rglob("*.json")}
        second = generate_f0001_context_sets(
            start_utc=start,
            end_exclusive_utc=end,
            locked_oos_start_utc=end,
            pit_store=pit,
            snapshot_root=snapshots,
            output_root=output,
            rules=load_signal_rules(),
        )

    assert first == second
    assert first["direction"] is None
    assert set(first["variants"]) == {
        "combined",
        "without_funding_stress",
        "without_oi_buildup",
    }
    assert before == {path: path.read_bytes() for path in output.rglob("*.json")}
    for variant in first["variants"]:
        manifest = json.loads((output / variant / "context-set.json").read_text())
        assert manifest["variant"] == variant
        assert manifest["context_count"] == 2
        assert len(manifest["rules_sha256"]) == 64
        assert manifest["locked_oos_start_utc"] == "2024-01-01T02:00:00Z"
        for item in (output / variant / "v1").rglob("*.json"):
            assert json.loads(item.read_text())["snapshot"]["direction"] is None


def test_rejects_locked_oos_access_before_reading_pit(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    with PointInTimeStore() as pit, pytest.raises(ValueError, match="Locked OOS"):
        generate_f0001_context_sets(
            start_utc=start,
            end_exclusive_utc=start + timedelta(hours=2),
            locked_oos_start_utc=start + timedelta(hours=1),
            pit_store=pit,
            snapshot_root=tmp_path / "snapshots",
            output_root=tmp_path / "contexts",
            rules=load_signal_rules(),
        )


def test_mcp_locked_boundary_matches_signal_preregistration():
    repo = Path(__file__).resolve().parents[3]
    signal_config = yaml.safe_load(
        (repo / "services/radar-signal/config/fragility_calibration.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert (
        load_f0001_locked_oos().isoformat().replace("+00:00", "Z")
        == signal_config["boundaries"]["locked_oos_start_utc"]
    )
