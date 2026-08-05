import json
from pathlib import Path

import pytest

from scripts.registrylib import phase2_trial_count_for_dsr, unique_phase2_trials_for_dsr
from scripts.statistical_gates import (
    StatisticalGateError,
    build_sensitivity_plan,
    evaluate_ablation,
    evaluate_dsr_gate,
    evaluate_pbo_cscv,
    evaluate_period_venue_fragility,
    evaluate_sensitivity,
)


def test_dsr_uses_registry_count_and_penalizes_more_trials():
    returns = {
        "candidate": [0.01, 0.02, -0.005, 0.015, 0.007, 0.012, -0.002, 0.009],
        "control": [0.001, -0.001, 0.002, -0.002, 0.001, -0.001, 0.002, -0.002],
    }
    few = evaluate_dsr_gate(
        returns_by_trial=returns,
        observed_trial_id="candidate",
        registry_trial_count=2,
        confidence_threshold=0.95,
    )
    many_returns = dict(returns)
    for index in range(18):
        scale = 1 + index / 20
        many_returns[f"control-{index:02d}"] = [scale * value for value in returns["control"]]
    many = evaluate_dsr_gate(
        returns_by_trial=many_returns,
        observed_trial_id="candidate",
        registry_trial_count=20,
        confidence_threshold=0.95,
    )
    assert few["registry_trial_count"] == 2
    assert few["dsr_probability"] > many["dsr_probability"]


def test_dsr_rejects_matrix_not_backed_by_registry():
    with pytest.raises(StatisticalGateError, match="tam eşleşmeli"):
        evaluate_dsr_gate(
            returns_by_trial={
                "a": [0.1, -0.1, 0.2],
                "b": [0.2, -0.1, 0.1],
                "c": [0.1, 0.2, -0.1],
            },
            observed_trial_id="a",
            registry_trial_count=2,
            confidence_threshold=0.95,
        )


def test_pbo_detects_selection_that_reverses_out_of_sample():
    report = evaluate_pbo_cscv(
        returns_by_configuration={
            "alternating_a": [0.10] * 4 + [-0.10] * 4,
            "alternating_b": [-0.10] * 4 + [0.10] * 4,
        },
        partitions=4,
        max_combinations=6,
        rejection_threshold=0.50,
    )
    assert report["pbo"] >= 0.50
    assert report["status"] == "failed"
    assert report["combinations"] == 6


def test_pbo_is_deterministic_and_budgeted():
    kwargs = dict(
        returns_by_configuration={
            "a": [0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02],
            "b": [-0.01, 0.00, -0.01, 0.00, -0.01, 0.00, -0.01, 0.00],
        },
        partitions=4,
        max_combinations=6,
        rejection_threshold=0.50,
    )
    outputs = {json.dumps(evaluate_pbo_cscv(**kwargs), sort_keys=True) for _ in range(100)}
    assert len(outputs) == 1
    with pytest.raises(StatisticalGateError, match="bütçeyi"):
        evaluate_pbo_cscv(**{**kwargs, "max_combinations": 5})
    with pytest.raises(StatisticalGateError, match="tam bölünmeli"):
        evaluate_pbo_cscv(
            **{
                **kwargs,
                "returns_by_configuration": {
                    "a": [0.01] * 9,
                    "b": [-0.01] * 9,
                },
            }
        )


def test_sensitivity_plan_is_exact_plus_minus_twenty_percent():
    plan = build_sensitivity_plan({"window_days": 30, "upper_percentile": 0.8}, relative_delta=0.20)
    values = {row["variant_id"]: row["varied_value"] for row in plan}
    assert values == {
        "upper_percentile:minus": pytest.approx(0.64),
        "upper_percentile:plus": pytest.approx(0.96),
        "window_days:minus": 24,
        "window_days:plus": 36,
    }


def test_sensitivity_requires_all_variants_and_both_cost_scenarios():
    expected = ["window:minus", "window:plus"]
    report = evaluate_sensitivity(
        base_metrics={"realistic": 0.10, "taker_heavy": 0.08},
        variant_metrics={
            "window:minus": {"realistic": 0.09, "taker_heavy": 0.07},
            "window:plus": {"realistic": 0.05, "taker_heavy": 0.03},
        },
        expected_variant_ids=expected,
        required_scenarios=["realistic", "taker_heavy"],
        min_retention_ratio=0.80,
    )
    assert report["status"] == "failed"
    assert "window:plus:realistic" in report["failures"]
    with pytest.raises(StatisticalGateError, match="tam eşleşmiyor"):
        evaluate_sensitivity(
            base_metrics={"realistic": 0.1, "taker_heavy": 0.08},
            variant_metrics={"window:minus": {"realistic": 0.09, "taker_heavy": 0.07}},
            expected_variant_ids=expected,
            required_scenarios=["realistic", "taker_heavy"],
            min_retention_ratio=0.8,
        )


def test_ablation_is_paired_and_fails_non_contributing_family():
    report = evaluate_ablation(
        full_returns={
            "realistic": [0.03, 0.02, 0.01, 0.02],
            "taker_heavy": [0.02, 0.01, 0.005, 0.01],
        },
        without_family_returns={
            "funding": {
                "realistic": [0.01, 0.01, 0.00, 0.01],
                "taker_heavy": [0.01, 0.00, 0.00, 0.00],
            },
            "volume": {
                "realistic": [0.04, 0.03, 0.02, 0.03],
                "taker_heavy": [0.03, 0.02, 0.01, 0.02],
            },
        },
        required_scenarios=["realistic", "taker_heavy"],
        min_mean_contribution=0.0,
        min_positive_fold_ratio=0.60,
    )
    assert report["status"] == "failed"
    assert "volume:realistic" in report["failures"]
    assert "funding:realistic" not in report["failures"]


def _fragility_kwargs() -> dict:
    def scenarios(value: float) -> dict[str, list[float]]:
        return {
            "realistic": [value, value * 1.1, value * 0.9],
            "taker_heavy": [value * 0.8, value * 0.9, value * 0.7],
        }

    return {
        "period_returns": {
            "early": scenarios(0.010),
            "middle": scenarios(0.012),
            "late": scenarios(0.009),
        },
        "venue_returns": {
            "binance": scenarios(0.010),
            "independent_venue": scenarios(0.009),
        },
        "required_scenarios": ["realistic", "taker_heavy"],
        "min_period_groups": 3,
        "min_venue_groups": 2,
        "min_observations_per_group": 3,
        "min_worst_group_retention_ratio": 0.50,
        "min_positive_group_ratio": 0.67,
    }


def test_period_venue_fragility_passes_balanced_groups_deterministically():
    kwargs = _fragility_kwargs()
    outputs = {
        json.dumps(evaluate_period_venue_fragility(**kwargs), sort_keys=True) for _ in range(100)
    }
    assert len(outputs) == 1
    report = evaluate_period_venue_fragility(**kwargs)
    assert report["status"] == "passed"
    assert report["period"]["status"] == "passed"
    assert report["venue"]["status"] == "passed"


def test_period_venue_fragility_exposes_weak_slice_and_both_costs():
    kwargs = _fragility_kwargs()
    kwargs["period_returns"]["late"]["taker_heavy"] = [-0.002, -0.001, -0.003]
    report = evaluate_period_venue_fragility(**kwargs)
    assert report["status"] == "failed"
    assert "period:taker_heavy" in report["period"]["failures"]
    assert report["period"]["rows"][1]["scenario"] == "taker_heavy"


def test_period_venue_fragility_fails_loud_on_missing_or_short_groups():
    kwargs = _fragility_kwargs()
    del kwargs["venue_returns"]["independent_venue"]
    with pytest.raises(StatisticalGateError, match="en az 2 grup"):
        evaluate_period_venue_fragility(**kwargs)

    kwargs = _fragility_kwargs()
    kwargs["period_returns"]["early"]["realistic"] = [0.01, 0.02]
    with pytest.raises(StatisticalGateError, match="en az 3 gözlem"):
        evaluate_period_venue_fragility(**kwargs)


def _registry_row(experiment_id: str, *, verdict: str, hypothesis: str, code: str) -> dict:
    return {
        "experiment_id": experiment_id,
        "hypothesis_id": hypothesis,
        "strategy_version": code,
        "dataset_snapshot": "dataset-1",
        "exit_code": 0,
        "result": {"performance": {}},
        "verdict": verdict,
    }


def test_phase2_registry_count_excludes_invalid_and_deduplicates(tmp_path: Path):
    registry = tmp_path / "experiments.jsonl"
    rows = [
        _registry_row("E-1", verdict="rejected", hypothesis="S-0003", code="code-1"),
        _registry_row("E-2", verdict="rejected", hypothesis="S-0003", code="code-1"),
        _registry_row("E-3", verdict="rejected", hypothesis="S-0004", code="code-2"),
        {"experiment_id": "OLD", "hypothesis_id": "S-0001", "verdict": "rejected"},
    ]
    registry.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    events = tmp_path / "verdict_events.jsonl"
    events.write_text(
        json.dumps(
            {
                "event_id": "V-1",
                "experiment_id": "E-2",
                "created_at_utc": "2026-08-05T00:00:00Z",
                "verdict": "invalid",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert phase2_trial_count_for_dsr(registry) == 2
    assert [row["experiment_id"] for row in unique_phase2_trials_for_dsr(registry)] == [
        "E-1",
        "E-3",
    ]
