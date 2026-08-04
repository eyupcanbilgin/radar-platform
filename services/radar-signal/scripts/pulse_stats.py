"""Time-series-safe helpers for the hypothesis pulse workbench.

The workbench is a rejection gate, so its null model must preserve the most important
dependence in market returns. These helpers use a circular moving-block bootstrap and
keep overlapping signal horizons out of the effective event sample.
"""

from __future__ import annotations

import math

import numpy as np

_MAX_BOOTSTRAP_CELLS = 2_000_000


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Adjust finite p-values with Benjamini-Hochberg FDR.

    Invalid/NaN tests remain NaN and are not counted in the multiple-testing universe.
    """
    result = [float("nan")] * len(p_values)
    valid = [(index, float(value)) for index, value in enumerate(p_values) if np.isfinite(value)]
    if not valid:
        return result

    valid.sort(key=lambda item: item[1])
    m = len(valid)
    adjusted = [1.0] * m
    cumulative_minimum = 1.0
    for rank_index in range(m - 1, -1, -1):
        _, p_value = valid[rank_index]
        rank = rank_index + 1
        adjusted_value = min(cumulative_minimum, p_value * m / rank)
        cumulative_minimum = adjusted_value
        adjusted[rank_index] = min(1.0, max(0.0, adjusted_value))

    for rank_index, (original_index, _) in enumerate(valid):
        result[original_index] = float(adjusted[rank_index])
    return result


def non_overlapping_positions(mask: np.ndarray, horizon: int) -> np.ndarray:
    """Return chronological event positions whose forward windows do not overlap."""
    if horizon < 1:
        raise ValueError("horizon en az 1 olmalı")
    candidates = np.flatnonzero(np.asarray(mask, dtype=bool))
    selected: list[int] = []
    last_position = -horizon
    for position in candidates:
        if position - last_position >= horizon:
            selected.append(int(position))
            last_position = int(position)
    return np.asarray(selected, dtype=int)


def _moving_block_null_means(
    base: np.ndarray,
    sample_size: int,
    long_share: float,
    n_bootstrap: int,
    rng: np.random.Generator,
    mode: str,
    block_size: int,
) -> np.ndarray:
    """Generate circular moving-block bootstrap means with bounded memory use."""
    block_size = min(max(1, int(block_size)), len(base))
    block_count = math.ceil(sample_size / block_size)
    cells_per_draw = block_count * block_size
    batch_size = max(1, min(n_bootstrap, _MAX_BOOTSTRAP_CELLS // cells_per_draw))
    offsets = np.arange(block_size, dtype=int)
    null_means = np.empty(n_bootstrap, dtype=float)

    for batch_start in range(0, n_bootstrap, batch_size):
        current_batch = min(batch_size, n_bootstrap - batch_start)
        starts = rng.integers(0, len(base), size=(current_batch, block_count))
        indices = (starts[..., None] + offsets) % len(base)
        sampled = base[indices]
        if mode == "directional":
            block_signs = np.where(
                rng.random((current_batch, block_count, 1)) < long_share,
                1.0,
                -1.0,
            )
            sampled = sampled * block_signs
        elif mode != "level":
            raise ValueError(f"geçersiz bootstrap modu: {mode}")
        flattened = sampled.reshape(current_batch, -1)[:, :sample_size]
        null_means[batch_start : batch_start + current_batch] = flattened.mean(axis=1)
    return null_means


def moving_block_test(
    signal_values: np.ndarray,
    base: np.ndarray,
    long_share: float,
    n_bootstrap: int,
    rng: np.random.Generator,
    *,
    mode: str = "directional",
    block_size: int = 4,
) -> dict[str, float]:
    """Compare an event mean with a horizon-matched moving-block null distribution."""
    signal_values = np.asarray(signal_values, dtype=float)
    signal_values = signal_values[np.isfinite(signal_values)]
    base = np.asarray(base, dtype=float)
    base = base[np.isfinite(base)]
    if len(signal_values) == 0 or len(base) < 2:
        return {
            "p_greater": float("nan"),
            "p_less": float("nan"),
            "p_two_sided": float("nan"),
            "null_mean": float("nan"),
            "null_std": float("nan"),
        }
    if n_bootstrap < 1:
        raise ValueError("bootstrap tekrar sayısı en az 1 olmalı")
    if not 0.0 <= long_share <= 1.0:
        raise ValueError("long_share 0 ile 1 arasında olmalı")

    null_means = _moving_block_null_means(
        base,
        len(signal_values),
        long_share,
        n_bootstrap,
        rng,
        mode,
        block_size,
    )
    observed = float(signal_values.mean())
    null_center = float(null_means.mean())
    p_greater = float(((null_means >= observed).sum() + 1) / (n_bootstrap + 1))
    p_less = float(((null_means <= observed).sum() + 1) / (n_bootstrap + 1))
    observed_distance = abs(observed - null_center)
    p_two_sided = float(
        ((np.abs(null_means - null_center) >= observed_distance).sum() + 1) / (n_bootstrap + 1)
    )
    return {
        "p_greater": p_greater,
        "p_less": p_less,
        "p_two_sided": p_two_sided,
        "null_mean": null_center,
        "null_std": float(null_means.std(ddof=1)) if n_bootstrap > 1 else 0.0,
    }
