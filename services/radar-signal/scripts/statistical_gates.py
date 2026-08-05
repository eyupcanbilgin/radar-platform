"""Fail-closed Phase-2 statistical gates: DSR, PBO/CSCV, sensitivity and ablation."""

import math
from itertools import combinations
from statistics import fmean, pstdev, variance

from scripts.dsr import deflated_sharpe


class StatisticalGateError(ValueError):
    """Statistical input is incomplete, inconsistent or unsafe to interpret."""


def _finite_series(values: list[float], *, name: str, minimum: int = 2) -> list[float]:
    if len(values) < minimum:
        raise StatisticalGateError(f"{name} en az {minimum} gözlem taşımalı")
    result = [float(value) for value in values]
    if any(not math.isfinite(value) for value in result):
        raise StatisticalGateError(f"{name} sonlu olmayan gözlem taşıyor")
    return result


def sharpe_ratio(values: list[float]) -> float:
    series = _finite_series(values, name="returns")
    sigma = pstdev(series)
    if sigma == 0:
        raise StatisticalGateError("Sharpe sabit getiri serisinde tanımsızdır")
    return fmean(series) / sigma


def evaluate_dsr_gate(
    *,
    returns_by_trial: dict[str, list[float]],
    observed_trial_id: str,
    registry_trial_count: int,
    confidence_threshold: float,
) -> dict:
    if observed_trial_id not in returns_by_trial:
        raise StatisticalGateError("observed_trial_id getiri matrisinde yok")
    if registry_trial_count < 2:
        raise StatisticalGateError("DSR için Registry en az 2 benzersiz Faz 2 denemesi ister")
    if registry_trial_count != len(returns_by_trial):
        raise StatisticalGateError("getiri matrisi Registry deneme evreniyle tam eşleşmeli")
    if not 0 < confidence_threshold < 1:
        raise StatisticalGateError("DSR confidence_threshold 0 ile 1 arasında olmalı")
    lengths = {len(values) for values in returns_by_trial.values()}
    if len(lengths) != 1:
        raise StatisticalGateError("DSR deneme getirileri eşit uzunlukta olmalı")
    sharpes = {
        trial_id: sharpe_ratio(values) for trial_id, values in sorted(returns_by_trial.items())
    }
    if len(sharpes) < 2:
        raise StatisticalGateError("Sharpe varyansı için en az 2 getiri serisi gerekir")
    sr_variance = variance(sharpes.values())
    observed = _finite_series(
        returns_by_trial[observed_trial_id], name="observed_returns", minimum=3
    )
    mean = fmean(observed)
    sigma = pstdev(observed)
    skew = fmean([(value - mean) ** 3 for value in observed]) / sigma**3
    kurtosis = fmean([(value - mean) ** 4 for value in observed]) / sigma**4
    probability = deflated_sharpe(
        observed_sharpe=sharpes[observed_trial_id],
        n_trials=registry_trial_count,
        sr_variance=sr_variance,
        n_observations=len(observed),
        skew=skew,
        kurtosis=kurtosis,
    )
    return {
        "status": "passed" if probability >= confidence_threshold else "failed",
        "observed_trial_id": observed_trial_id,
        "registry_trial_count": registry_trial_count,
        "matrix_trial_count": len(sharpes),
        "observed_sharpe": sharpes[observed_trial_id],
        "sharpe_variance": sr_variance,
        "dsr_probability": probability,
        "confidence_threshold": confidence_threshold,
    }


def _partition_indices(length: int, partitions: int) -> list[list[int]]:
    if partitions < 4 or partitions % 2:
        raise StatisticalGateError("PBO partitions çift ve en az 4 olmalı")
    if length < partitions:
        raise StatisticalGateError("PBO gözlem sayısı partition sayısından az olamaz")
    if length % partitions:
        raise StatisticalGateError("PBO eşit partition için gözlem sayısı tam bölünmeli")
    base = length // partitions
    blocks = []
    start = 0
    for _ in range(partitions):
        blocks.append(list(range(start, start + base)))
        start += base
    return blocks


def _mean_at(values: list[float], indices: list[int]) -> float:
    return fmean(values[index] for index in indices)


def evaluate_pbo_cscv(
    *,
    returns_by_configuration: dict[str, list[float]],
    partitions: int,
    max_combinations: int,
    rejection_threshold: float,
) -> dict:
    if len(returns_by_configuration) < 2:
        raise StatisticalGateError("PBO en az 2 konfigürasyon ister")
    if not 0 <= rejection_threshold <= 1:
        raise StatisticalGateError("PBO rejection_threshold [0,1] aralığında olmalı")
    names = sorted(returns_by_configuration)
    series = {
        name: _finite_series(returns_by_configuration[name], name=f"returns:{name}")
        for name in names
    }
    lengths = {len(values) for values in series.values()}
    if len(lengths) != 1:
        raise StatisticalGateError("PBO konfigürasyon getirileri eşit uzunlukta olmalı")
    blocks = _partition_indices(lengths.pop(), partitions)
    combos = list(combinations(range(partitions), partitions // 2))
    if max_combinations < 1 or len(combos) > max_combinations:
        raise StatisticalGateError(
            f"PBO kombinasyon sayısı bütçeyi aşıyor: {len(combos)}>{max_combinations}"
        )
    lambdas = []
    selections = {name: 0 for name in names}
    all_blocks = set(range(partitions))
    for train_blocks in combos:
        train_idx = [i for block in train_blocks for i in blocks[block]]
        test_idx = [i for block in sorted(all_blocks - set(train_blocks)) for i in blocks[block]]
        train_scores = {name: _mean_at(values, train_idx) for name, values in series.items()}
        selected = max(names, key=lambda name: (train_scores[name], name))
        selections[selected] += 1
        test_scores = {name: _mean_at(values, test_idx) for name, values in series.items()}
        selected_score = test_scores[selected]
        less = sum(score < selected_score for score in test_scores.values())
        equal = sum(score == selected_score for score in test_scores.values())
        rank = less + (equal + 1) / 2
        relative_rank = rank / (len(names) + 1)
        lambdas.append(math.log(relative_rank / (1 - relative_rank)))
    pbo = sum(value <= 0 for value in lambdas) / len(lambdas)
    return {
        "status": "passed" if pbo < rejection_threshold else "failed",
        "pbo": pbo,
        "rejection_threshold": rejection_threshold,
        "combinations": len(combos),
        "partitions": partitions,
        "configuration_count": len(names),
        "performance_metric": "mean_net_return",
        "selection_counts": selections,
        "logit_rank_min": min(lambdas),
        "logit_rank_max": max(lambdas),
    }


def build_sensitivity_plan(
    base_parameters: dict[str, int | float], *, relative_delta: float
) -> list[dict]:
    if not 0 < relative_delta < 1:
        raise StatisticalGateError("relative_delta 0 ile 1 arasında olmalı")
    variants = []
    for name, value in sorted(base_parameters.items()):
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            raise StatisticalGateError(f"hassasiyet parametresi pozitif sayısal olmalı: {name}")
        for direction, factor in (("minus", 1 - relative_delta), ("plus", 1 + relative_delta)):
            varied = round(value * factor) if isinstance(value, int) else value * factor
            if varied == value or varied <= 0:
                raise StatisticalGateError(f"parametre için ayrışan ± varyant üretilemedi: {name}")
            variants.append(
                {
                    "variant_id": f"{name}:{direction}",
                    "parameter": name,
                    "direction": direction,
                    "base_value": value,
                    "varied_value": varied,
                }
            )
    if not variants:
        raise StatisticalGateError("hassasiyet planı en az bir parametre ister")
    return variants


def evaluate_sensitivity(
    *,
    base_metrics: dict[str, float],
    variant_metrics: dict[str, dict[str, float]],
    expected_variant_ids: list[str],
    required_scenarios: list[str],
    min_retention_ratio: float,
) -> dict:
    if not 0 < min_retention_ratio <= 1:
        raise StatisticalGateError("min_retention_ratio (0,1] aralığında olmalı")
    if required_scenarios != ["realistic", "taker_heavy"]:
        raise StatisticalGateError("realistic ve taker_heavy senaryoları birlikte zorunlu")
    if sorted(variant_metrics) != sorted(expected_variant_ids):
        raise StatisticalGateError("hassasiyet sonuçları plan varyantlarıyla tam eşleşmiyor")
    failures = []
    rows = []
    for scenario in required_scenarios:
        base = float(base_metrics.get(scenario, math.nan))
        if not math.isfinite(base) or base <= 0:
            raise StatisticalGateError(f"pozitif base metric eksik: {scenario}")
        for variant_id in sorted(expected_variant_ids):
            metric = float(variant_metrics[variant_id].get(scenario, math.nan))
            if not math.isfinite(metric):
                raise StatisticalGateError(f"varyant metriği eksik: {variant_id}/{scenario}")
            retention = metric / base
            passed = retention >= min_retention_ratio
            if not passed:
                failures.append(f"{variant_id}:{scenario}")
            rows.append(
                {
                    "variant_id": variant_id,
                    "scenario": scenario,
                    "metric": metric,
                    "retention_ratio": retention,
                    "passed": passed,
                }
            )
    return {"status": "passed" if not failures else "failed", "failures": failures, "rows": rows}


def evaluate_ablation(
    *,
    full_returns: dict[str, list[float]],
    without_family_returns: dict[str, dict[str, list[float]]],
    required_scenarios: list[str],
    min_mean_contribution: float,
    min_positive_fold_ratio: float,
) -> dict:
    if not 0 <= min_positive_fold_ratio <= 1:
        raise StatisticalGateError("min_positive_fold_ratio [0,1] aralığında olmalı")
    if required_scenarios != ["realistic", "taker_heavy"]:
        raise StatisticalGateError("realistic ve taker_heavy senaryoları birlikte zorunlu")
    rows = []
    failures = []
    for family in sorted(without_family_returns):
        for scenario in required_scenarios:
            full = _finite_series(full_returns.get(scenario, []), name=f"full:{scenario}")
            reduced = _finite_series(
                without_family_returns[family].get(scenario, []),
                name=f"without:{family}:{scenario}",
            )
            if len(full) != len(reduced):
                raise StatisticalGateError("ablation eşleşmiş fold uzunlukları farklı")
            contributions = [
                with_all - without for with_all, without in zip(full, reduced, strict=True)
            ]
            mean_contribution = fmean(contributions)
            positive_ratio = sum(value > 0 for value in contributions) / len(contributions)
            passed = (
                mean_contribution > min_mean_contribution
                and positive_ratio >= min_positive_fold_ratio
            )
            if not passed:
                failures.append(f"{family}:{scenario}")
            rows.append(
                {
                    "family": family,
                    "scenario": scenario,
                    "mean_contribution": mean_contribution,
                    "positive_fold_ratio": positive_ratio,
                    "passed": passed,
                }
            )
    if not rows:
        raise StatisticalGateError("ablation en az bir veri ailesi ister")
    return {"status": "passed" if not failures else "failed", "failures": failures, "rows": rows}


def _evaluate_fragility_dimension(
    *,
    dimension: str,
    grouped_returns: dict[str, dict[str, list[float]]],
    required_scenarios: list[str],
    min_groups: int,
    min_observations_per_group: int,
    min_worst_group_retention_ratio: float,
    min_positive_group_ratio: float,
) -> dict:
    if len(grouped_returns) < min_groups:
        raise StatisticalGateError(f"{dimension} kırılganlığı en az {min_groups} grup ister")
    if any(not str(name).strip() for name in grouped_returns):
        raise StatisticalGateError(f"{dimension} grup adı boş olamaz")

    rows = []
    failures = []
    names = sorted(grouped_returns)
    for scenario in required_scenarios:
        means = {}
        for name in names:
            series = _finite_series(
                grouped_returns[name].get(scenario, []),
                name=f"fragility:{dimension}:{name}:{scenario}",
                minimum=min_observations_per_group,
            )
            means[name] = fmean(series)
        reference = fmean(means.values())
        if reference <= 0:
            failures.append(f"{dimension}:{scenario}:non_positive_reference")
            retention = {name: 0.0 for name in names}
        else:
            retention = {name: value / reference for name, value in means.items()}
        worst_name = min(names, key=lambda name: (retention[name], name))
        worst_retention = retention[worst_name]
        positive_ratio = sum(value > 0 for value in means.values()) / len(means)
        passed = (
            reference > 0
            and worst_retention >= min_worst_group_retention_ratio
            and positive_ratio >= min_positive_group_ratio
        )
        if not passed and f"{dimension}:{scenario}:non_positive_reference" not in failures:
            failures.append(f"{dimension}:{scenario}")
        rows.append(
            {
                "dimension": dimension,
                "scenario": scenario,
                "group_means": means,
                "cross_group_mean": reference,
                "worst_group": worst_name,
                "worst_group_retention_ratio": worst_retention,
                "positive_group_ratio": positive_ratio,
                "passed": passed,
            }
        )
    return {"status": "passed" if not failures else "failed", "failures": failures, "rows": rows}


def evaluate_period_venue_fragility(
    *,
    period_returns: dict[str, dict[str, list[float]]],
    venue_returns: dict[str, dict[str, list[float]]],
    required_scenarios: list[str],
    min_period_groups: int,
    min_venue_groups: int,
    min_observations_per_group: int,
    min_worst_group_retention_ratio: float,
    min_positive_group_ratio: float,
) -> dict:
    """Require a candidate to survive pre-registered time and venue slices."""
    if required_scenarios != ["realistic", "taker_heavy"]:
        raise StatisticalGateError("realistic ve taker_heavy senaryoları birlikte zorunlu")
    if min_period_groups < 3 or min_venue_groups < 2 or min_observations_per_group < 2:
        raise StatisticalGateError("fragility grup ve gözlem alt sınırları geçersiz")
    if not 0 < min_worst_group_retention_ratio <= 1 or not 0 < min_positive_group_ratio <= 1:
        raise StatisticalGateError("fragility göreli eşikleri (0,1] aralığında olmalı")

    period = _evaluate_fragility_dimension(
        dimension="period",
        grouped_returns=period_returns,
        required_scenarios=required_scenarios,
        min_groups=min_period_groups,
        min_observations_per_group=min_observations_per_group,
        min_worst_group_retention_ratio=min_worst_group_retention_ratio,
        min_positive_group_ratio=min_positive_group_ratio,
    )
    venue = _evaluate_fragility_dimension(
        dimension="venue",
        grouped_returns=venue_returns,
        required_scenarios=required_scenarios,
        min_groups=min_venue_groups,
        min_observations_per_group=min_observations_per_group,
        min_worst_group_retention_ratio=min_worst_group_retention_ratio,
        min_positive_group_ratio=min_positive_group_ratio,
    )
    return {
        "status": "passed" if period["status"] == venue["status"] == "passed" else "failed",
        "period": period,
        "venue": venue,
    }
