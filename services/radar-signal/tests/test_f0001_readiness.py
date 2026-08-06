"""F-0001 readiness tests use only synthetic decision contexts."""

import copy
from datetime import UTC, datetime, timedelta

from scripts.f0001_readiness import build_readiness_report
from scripts.fragility_calibration import load_fragility_config


def _contexts(hours: int, *, include_values: bool = True) -> list[dict]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(hours):
        stamp = (start + timedelta(hours=index)).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "as_of_utc": stamp,
                "snapshot": {
                    "data_cutoff_at_utc": stamp,
                    "fragility": float((index * 17) % 101) if include_values else None,
                    "direction": None,
                },
                "data_quality": {"directional_decision_allowed": False},
            }
        )
    return rows


def _config() -> dict:
    config = copy.deepcopy(load_fragility_config())
    config["trigger"].update(
        rolling_lookback_days=2,
        min_history_days=1,
        min_observations=24,
        episode_cooldown_hours=6,
    )
    config["validation"]["min_triggered_events_per_venue"] = 2
    return config


def test_readiness_is_directionless_deterministic_and_registry_free():
    contexts = _contexts(120)
    report = build_readiness_report(
        context_sets={
            "combined": contexts,
            "without_funding_stress": contexts,
            "without_oi_buildup": contexts,
        },
        context_set_sha256={
            "combined": "a" * 64,
            "without_funding_stress": "b" * 64,
            "without_oi_buildup": "c" * 64,
        },
        config=_config(),
    )

    assert report["measurement_ready"] is True
    assert report["direction"] is None
    assert report["locked_oos_opened"] is False
    assert report["registry_write"] is False
    assert all(item["independent_triggered_events"] >= 2 for item in report["variants"].values())


def test_null_fragility_is_blocker_not_neutral_context():
    ready = _contexts(120)
    unavailable = _contexts(120, include_values=False)
    report = build_readiness_report(
        context_sets={
            "combined": ready,
            "without_funding_stress": unavailable,
            "without_oi_buildup": ready,
        },
        context_set_sha256={
            "combined": "a" * 64,
            "without_funding_stress": "b" * 64,
            "without_oi_buildup": "c" * 64,
        },
        config=_config(),
    )

    variant = report["variants"]["without_funding_stress"]
    assert report["measurement_ready"] is False
    assert variant["usable_fragility_contexts"] == 0
    assert variant["trigger_eligible_contexts"] == 0
    assert variant["independent_triggered_events"] == 0
    assert "trigger_history_unavailable" in variant["blockers"]
