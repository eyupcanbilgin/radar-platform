"""config yükleme sözleşme testleri: fail-loud doğrulama + hash izlenebilirliği."""

from pathlib import Path
from textwrap import dedent

import pytest

from btc_radar.core import config


def test_weights_load_and_sum():
    w = config.load_weights()
    assert abs(sum(w.layers.values()) - 1.0) < 1e-9
    assert w.confidence.insufficient_below == 55


def test_signal_rules_load():
    r = config.load_signal_rules()
    assert r.version
    # Kurallar artık gerçek: her kural tanımlı bir feature'a ve yeterli-geçmiş şartına bağlı.
    assert {rule.id for rule in r.rules} == {"funding_stress", "oi_buildup"}
    assert set(r.features) == {"funding_stress", "oi_buildup"}
    assert r.publication_lag_seconds > 0


def test_rule_referencing_an_undefined_feature_fails_loud(tmp_path: Path):
    bad = tmp_path / "signal_rules.yaml"
    bad.write_text(
        dedent(
            """
            version: 'x'
            features: {}
            rules:
              - id: r1
                layer: derivatives
                feature: yok
                fragility_bands:
                  - {min_percentile: 0.0, r: 0.0}
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="tanımsız feature"):
        config.load_signal_rules(bad)


def test_fragility_bands_must_be_descending_with_a_catch_all(tmp_path: Path):
    bad = tmp_path / "signal_rules.yaml"
    bad.write_text(
        dedent(
            """
            version: 'x'
            features:
              f:
                kind: abs_percentile
                metric: m
                lookback_days: 1
                expected_period_seconds: 60
                min_samples: 2
                min_span_days: 0
                max_gap_seconds: 60
            rules:
              - id: r1
                layer: derivatives
                feature: f
                fragility_bands:
                  - {min_percentile: 50.0, r: 1.0}
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="yakalayıcı bant"):
        config.load_signal_rules(bad)


def test_change_window_must_match_the_feature_kind(tmp_path: Path):
    bad = tmp_path / "signal_rules.yaml"
    bad.write_text(
        dedent(
            """
            version: 'x'
            features:
              f:
                kind: change_abs_percentile
                metric: m
                lookback_days: 1
                expected_period_seconds: 60
                min_samples: 2
                min_span_days: 0
                max_gap_seconds: 60
            rules: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="change_window_seconds zorunlu"):
        config.load_signal_rules(bad)


def test_weights_hash_deterministic():
    assert config.weights_hash() == config.weights_hash()
    assert len(config.weights_hash()) == 12


def test_broken_weights_sum_fails_loud(tmp_path: Path):
    bad = tmp_path / "weights.yaml"
    bad.write_text(
        "version: 'x'\nlayers:\n  a: 0.5\n  b: 0.6\nconfidence:\n  insufficient_below: 55\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="1.0"):
        config.load_weights(bad)


def test_empty_yaml_fails_loud(tmp_path: Path):
    empty = tmp_path / "weights.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="boş"):
        config.load_weights(empty)
