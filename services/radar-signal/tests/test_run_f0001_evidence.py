"""F-0001 evidence runner tests use only synthetic contexts and OHLCV."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from scripts.fragility_calibration import load_fragility_config
from scripts.run_f0001_evidence import (
    _load_contexts,
    _load_hourly_bars,
    _manifest_snapshot,
    _record_once,
    build_evidence,
)


def _synthetic_inputs(hours: int = 480):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    contexts = []
    bars = []
    price = 100.0
    for index in range(hours):
        as_of = start + timedelta(hours=index)
        timestamp = as_of.isoformat().replace("+00:00", "Z")
        fragility = float((index * 17) % 101)
        contexts.append(
            {
                "as_of_utc": timestamp,
                "data_cutoff_at_utc": timestamp,
                "snapshot": {"fragility": fragility, "direction": None},
                "gates": {"directional_decision_allowed": False},
            }
        )
        change = 0.006 if fragility >= 80 else 0.001
        price *= 1 + (change if index % 2 else -change / 2)
        bars.append(
            {
                "close_at_utc": timestamp,
                "available_at_utc": timestamp,
                "high": price * (1 + change),
                "low": price * (1 - change),
                "close": price,
            }
        )
    return contexts, bars


def _config():
    config = copy.deepcopy(load_fragility_config())
    config["boundaries"].update(
        development_start_utc="2024-01-01T00:00:00Z",
        locked_oos_start_utc="2024-01-21T00:00:00Z",
    )
    config["trigger"].update(
        rolling_lookback_days=3,
        min_history_days=1,
        min_observations=24,
        episode_cooldown_hours=6,
    )
    config["outcome"].update(
        horizon_hours=6,
        trailing_volatility_hours=6,
        label_distribution_lookback_days=5,
        min_settled_labels=12,
    )
    config["validation"].update(
        train_window_days=5,
        test_window_days=3,
        step_days=3,
        embargo_days=1,
        min_triggered_events_per_venue=2,
    )
    return config


def test_build_evidence_is_directionless_and_deterministic():
    contexts, bars = _synthetic_inputs()
    kwargs = {
        "contexts": contexts,
        "bars_by_venue": {"binance_futures": bars, "coinbase_spot": bars},
        "config": _config(),
        "dataset_snapshot": "dataset-1",
        "code_sha": "abc123def456",
        "ablation_contexts": {
            "without_funding_stress": contexts,
            "without_oi_buildup": contexts,
        },
    }

    first = build_evidence(**kwargs)
    second = build_evidence(**kwargs)

    assert first == second
    assert first["direction"] is None
    assert first["status"] in {"passed", "rejected", "unavailable"}
    assert first["calibration"]["direction"] is None
    assert set(first["ablations"]) == {"without_funding_stress", "without_oi_buildup"}
    assert set(first["event_row_counts"]) == {"binance_futures", "coinbase_spot"}


def test_loaders_map_feather_open_time_to_close_time_and_accept_context_directory(tmp_path):
    context_dir = tmp_path / "contexts"
    context_dir.mkdir()
    (context_dir / "b.json").write_text(json.dumps({"as_of_utc": "b"}), encoding="utf-8")
    (context_dir / "a.json").write_text(json.dumps([{"as_of_utc": "a"}]), encoding="utf-8")
    feather = tmp_path / "bars.feather"
    pd.DataFrame(
        {
            "date": [datetime(2024, 1, 1, tzinfo=UTC)],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
        }
    ).to_feather(feather)

    assert [row["as_of_utc"] for row in _load_contexts(context_dir)] == ["a", "b"]
    assert _load_hourly_bars(feather)[0]["close_at_utc"] == "2024-01-01T01:00:00Z"


def test_manifest_requires_verified_declared_inputs(tmp_path, monkeypatch):
    user_dir = tmp_path / "user_data"
    binance = user_dir / "data" / "binance" / "btc.feather"
    coinbase = user_dir / "data" / "coinbase" / "btc.feather"
    binance.parent.mkdir(parents=True)
    coinbase.parent.mkdir(parents=True)
    binance.write_bytes(b"binance")
    coinbase.write_bytes(b"coinbase")
    monkeypatch.setenv("RADAR_SIGNAL_USERDIR", str(user_dir))
    entries = [
        {
            "file": str(path.relative_to(tmp_path)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in (binance, coinbase)
    ]
    manifest = tmp_path / "MANIFEST-20260806.json"
    manifest.write_text(
        json.dumps({"manifest_sha256": "snapshot-1", "files": entries}), encoding="utf-8"
    )

    assert _manifest_snapshot(manifest, [binance, coinbase]) == "snapshot-1"

    coinbase.write_bytes(b"changed")
    try:
        _manifest_snapshot(manifest, [binance, coinbase])
    except ValueError as error:
        assert "hash_mismatch" in str(error)
    else:
        raise AssertionError("hash sapması kabul edilmemeliydi")


def test_registry_deduplicates_same_hypothesis_code_and_dataset(monkeypatch, tmp_path):
    evidence = {
        "code_sha": "abc123def456",
        "dataset_snapshot": "dataset-1",
        "status": "rejected",
        "calibration": {"status": "rejected"},
    }
    existing = {
        "experiment_id": "E-existing",
        "hypothesis_id": "F-0001",
        "strategy_version": "abc123def456",
        "dataset_snapshot": "dataset-1",
        "verdict": "rejected",
    }
    monkeypatch.setattr("scripts.run_f0001_evidence.read_all", lambda _: [existing])
    monkeypatch.setattr(
        "scripts.run_f0001_evidence.record_run",
        lambda **_: (_ for _ in ()).throw(AssertionError("duplicate kayıt yazılmamalı")),
    )

    assert _record_once(evidence, registry_path=tmp_path / "registry.jsonl") == existing
