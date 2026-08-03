"""DSR testleri + KABUL TESTİ: DSR'ın N girdisi registry sayımıyla eşleşir (P0-2)."""

from pathlib import Path

import pytest
from dsr import deflated_sharpe, expected_max_sharpe, verdict

from registrylib import count_runs, record_run, trials_for_dsr


def _run(tmp: Path, family="S-0001", **over):
    base = dict(
        strategy="S0001EmaCross",
        hypothesis_id=family,
        scenario="realistic",
        effective_fee=0.00085,
        exit_code=0,
    )
    base.update(over)
    return record_run(registry_path=tmp / "experiments.jsonl", **base)


# --- SR0: şansla beklenen en yüksek Sharpe ---------------------------------------------
def test_expected_max_sharpe_grows_with_trials():
    """Ne kadar çok denersen, şansla o kadar yüksek Sharpe beklenir."""
    few = expected_max_sharpe(n_trials=5, sr_variance=0.25)
    many = expected_max_sharpe(n_trials=500, sr_variance=0.25)
    assert 0 < few < many


def test_zero_variance_means_no_selection_bias():
    assert expected_max_sharpe(n_trials=100, sr_variance=0.0) == 0.0


def test_single_trial_fails_loud():
    with pytest.raises(ValueError, match="n_trials"):
        expected_max_sharpe(n_trials=1, sr_variance=0.25)


# --- DSR ------------------------------------------------------------------------------
def test_strong_sharpe_survives_few_trials():
    dsr = deflated_sharpe(observed_sharpe=2.5, n_trials=5, sr_variance=0.1, n_observations=500)
    assert dsr > 0.95
    assert verdict(dsr) == "anlamli"


def test_same_sharpe_dies_under_many_trials():
    """Aynı Sharpe, 5 denemede anlamlı; 5000 denemede şans."""
    common = dict(observed_sharpe=1.2, sr_variance=0.5, n_observations=250)
    assert deflated_sharpe(n_trials=5, **common) > deflated_sharpe(n_trials=5000, **common)
    assert verdict(deflated_sharpe(n_trials=5000, **common)) == "sans"


def test_negative_sharpe_is_never_significant():
    dsr = deflated_sharpe(observed_sharpe=-0.8, n_trials=10, sr_variance=0.2, n_observations=300)
    assert dsr < 0.5 and verdict(dsr) == "sans"


def test_more_observations_increase_confidence():
    common = dict(observed_sharpe=1.5, n_trials=10, sr_variance=0.2)
    assert deflated_sharpe(n_observations=1000, **common) > deflated_sharpe(
        n_observations=50, **common
    )


def test_too_few_observations_fails_loud():
    with pytest.raises(ValueError, match="n_observations"):
        deflated_sharpe(observed_sharpe=1.0, n_trials=5, sr_variance=0.1, n_observations=1)


def test_impossible_moments_fail_loud():
    with pytest.raises(ValueError, match="payda tanımsız"):
        deflated_sharpe(
            observed_sharpe=3.0,
            n_trials=5,
            sr_variance=0.1,
            n_observations=100,
            skew=5.0,
            kurtosis=3.0,
        )


# --- KABUL TESTİ (P0-2): N registry'den gelir -------------------------------------------
def test_dsr_trials_match_registry_count(tmp_path: Path):
    reg = tmp_path / "experiments.jsonl"
    for _ in range(7):
        _run(tmp_path)
    _run(tmp_path, family="S-0002")  # başka aile karışmamalı

    assert count_runs("S-0001", registry_path=reg) == 7
    assert trials_for_dsr("S-0001", registry_path=reg) == 7
    assert trials_for_dsr("S-0001", registry_path=reg) == count_runs("S-0001", registry_path=reg)


def test_rejected_and_failed_runs_still_count(tmp_path: Path):
    """Çoklu-deneme düzeltmesi 'kaç kez denedik' sorusudur; ret de denemedir."""
    reg = tmp_path / "experiments.jsonl"
    _run(tmp_path, verdict="accepted")
    _run(tmp_path, verdict="rejected")
    _run(tmp_path, exit_code=1)
    assert trials_for_dsr("S-0001", registry_path=reg) == 3


def test_dsr_refuses_unregistered_family(tmp_path: Path):
    _run(tmp_path)
    with pytest.raises(ValueError, match="DSR ≥2 deneme ister"):
        trials_for_dsr("S-0001", registry_path=tmp_path / "experiments.jsonl")


def test_n_cannot_be_hand_fed_end_to_end(tmp_path: Path):
    """Kullanım kalıbı: N doğrudan registry'den DSR'a akar, arada elle sayı yok."""
    reg = tmp_path / "experiments.jsonl"
    for _ in range(40):
        _run(tmp_path)
    n = trials_for_dsr("S-0001", registry_path=reg)
    dsr = deflated_sharpe(observed_sharpe=1.1, n_trials=n, sr_variance=0.4, n_observations=200)
    assert 0.0 <= dsr <= 1.0
    assert n == 40
