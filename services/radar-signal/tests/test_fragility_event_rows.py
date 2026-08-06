import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.fragility_calibration import FragilityCalibrationError, load_fragility_config
from scripts.fragility_event_rows import build_event_row_bundle


def _inputs(hours: int = 500):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    contexts = []
    bars = []
    price = 100.0
    for index in range(hours):
        close_at = start + timedelta(hours=index)
        fragility = float((index * 17) % 101)
        contexts.append(
            {
                "as_of_utc": close_at.isoformat().replace("+00:00", "Z"),
                "snapshot": {
                    "data_cutoff_at_utc": close_at.isoformat().replace("+00:00", "Z"),
                    "fragility": fragility,
                    "direction": None,
                },
                "data_quality": {"directional_decision_allowed": False},
            }
        )
        change = 0.004 if fragility >= 80 else 0.001
        price *= 1 + (change if index % 2 else -change / 2)
        bars.append(
            {
                "close_at_utc": close_at.isoformat().replace("+00:00", "Z"),
                "available_at_utc": close_at.isoformat().replace("+00:00", "Z"),
                "high": price * (1 + change),
                "low": price * (1 - change),
                "close": price,
            }
        )
    return contexts, bars


def _config():
    config = copy.deepcopy(load_fragility_config())
    config["trigger"].update(rolling_lookback_days=10, min_history_days=2, min_observations=48)
    config["outcome"].update(label_distribution_lookback_days=10, min_settled_labels=24)
    return config


def test_event_bundle_is_directionless_provenanced_and_deterministic():
    contexts, bars = _inputs()
    kwargs = {
        "contexts": contexts,
        "bars_by_venue": {"binance_futures": bars, "coinbase_spot": bars},
        "config": _config(),
        "provenance": {"dataset_snapshot": "synthetic", "code_sha": "test"},
    }
    outputs = {json.dumps(build_event_row_bundle(**kwargs), sort_keys=True) for _ in range(100)}
    assert len(outputs) == 1
    bundle = build_event_row_bundle(**kwargs)
    assert bundle["direction"] is None
    assert len(bundle["artifact_sha256"]) == 64
    assert all(bundle["rows_by_venue"].values())


def test_event_bundle_rejects_direction_lookahead_and_missing_venue():
    contexts, bars = _inputs()
    contexts[0]["snapshot"]["direction"] = 0
    with pytest.raises(FragilityCalibrationError, match="direction-null"):
        build_event_row_bundle(
            contexts=contexts,
            bars_by_venue={"binance_futures": bars, "coinbase_spot": bars},
            config=_config(),
            provenance={},
        )

    contexts, bars = _inputs()
    contexts[0]["snapshot"]["data_cutoff_at_utc"] = "2024-01-01T01:00:00Z"
    with pytest.raises(FragilityCalibrationError, match="look-ahead"):
        build_event_row_bundle(
            contexts=contexts,
            bars_by_venue={"binance_futures": bars, "coinbase_spot": bars},
            config=_config(),
            provenance={},
        )

    contexts, bars = _inputs()
    with pytest.raises(FragilityCalibrationError, match="venue OHLCV eksik"):
        build_event_row_bundle(
            contexts=contexts,
            bars_by_venue={"binance_futures": bars},
            config=_config(),
            provenance={},
        )


def test_venue_gaps_are_segmented_and_reported_without_fabricated_bars():
    contexts, bars = _inputs()
    gapped = bars[:200] + bars[205:]

    bundle = build_event_row_bundle(
        contexts=contexts,
        bars_by_venue={"binance_futures": bars, "coinbase_spot": gapped},
        config=_config(),
        provenance={"dataset_snapshot": "synthetic"},
    )

    coverage = bundle["venue_coverage"]["coinbase_spot"]
    assert coverage["missing_hours"] == 5
    assert coverage["segment_count"] == 2
    excluded = {
        (datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=index))
        .isoformat()
        .replace("+00:00", "Z")
        for index in range(176, 229)
    }
    assert not any(row["as_of_utc"] in excluded for row in bundle["rows_by_venue"]["coinbase_spot"])
