import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.fragility_calibration import (
    FragilityCalibrationError,
    evaluate_fragility_calibration,
    load_fragility_config,
)
from scripts.walk_forward_lib import LockedOOSAccessError


def _rows() -> list[dict]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(940):
        as_of = start + timedelta(days=index)
        triggered = index % 3 == 0
        event = triggered or index % 17 == 0
        rows.append(
            {
                "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
                "label_available_at_utc": (as_of + timedelta(hours=24))
                .isoformat()
                .replace("+00:00", "Z"),
                "triggered": triggered,
                "event": event,
            }
        )
    return rows


def _bundle() -> dict[str, list[dict]]:
    return {"binance_futures": _rows(), "coinbase_spot": _rows()}


def test_f0001_config_is_locked_and_directionless():
    config = load_fragility_config()
    assert config["version"] == "1.1"
    assert config["validation"]["metric_aggregation"] == "pooled_out_of_fold"
    assert config["validation"]["required_venues"] == ["binance_futures", "coinbase_spot"]


def test_calibration_passes_strong_synthetic_relation_deterministically():
    config = load_fragility_config()
    outputs = {
        json.dumps(evaluate_fragility_calibration(_bundle(), config), sort_keys=True)
        for _ in range(100)
    }
    assert len(outputs) == 1
    report = evaluate_fragility_calibration(_bundle(), config)
    assert report["status"] == "passed"
    assert report["direction"] is None
    assert all(item["brier_skill_score"] > 0 for item in report["venues"].values())


def test_missing_venue_and_small_sample_are_unavailable_not_neutral():
    config = load_fragility_config()
    report = evaluate_fragility_calibration({"binance_futures": _rows()}, config)
    assert report["status"] == "unavailable"
    assert report["blockers"] == ["missing_venue:coinbase_spot"]

    small = {venue: rows[:100] for venue, rows in _bundle().items()}
    report = evaluate_fragility_calibration(small, config)
    assert report["status"] == "unavailable"
    assert all(item["blockers"] for item in report["venues"].values())


def test_locked_oos_and_duplicate_rows_fail_loud():
    config = load_fragility_config()
    bundle = _bundle()
    bundle["binance_futures"].append(
        {
            "as_of_utc": "2026-08-04T00:00:00Z",
            "label_available_at_utc": "2026-08-05T00:00:00Z",
            "triggered": True,
            "event": True,
        }
    )
    with pytest.raises(LockedOOSAccessError):
        evaluate_fragility_calibration(bundle, config)

    bundle = _bundle()
    bundle["coinbase_spot"].append(copy.deepcopy(bundle["coinbase_spot"][0]))
    with pytest.raises(FragilityCalibrationError, match="duplicate"):
        evaluate_fragility_calibration(bundle, config)

    bundle = _bundle()
    bundle["binance_futures"][0]["label_available_at_utc"] = "2024-01-01T01:00:00Z"
    with pytest.raises(FragilityCalibrationError, match="dondurulmuş ufuktan"):
        evaluate_fragility_calibration(bundle, config)


def test_config_rejects_probability_method_drift(tmp_path):
    config = load_fragility_config()
    config["validation"]["probability_estimator"] = "post_hoc_best"
    path = tmp_path / "fragility.yaml"
    import yaml

    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(FragilityCalibrationError, match="ön-kayıt"):
        load_fragility_config(path)
