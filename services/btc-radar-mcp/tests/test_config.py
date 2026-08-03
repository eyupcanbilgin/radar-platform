"""config yükleme sözleşme testleri: fail-loud doğrulama + hash izlenebilirliği."""

from pathlib import Path

import pytest

from btc_radar.core import config


def test_weights_load_and_sum():
    w = config.load_weights()
    assert abs(sum(w.layers.values()) - 1.0) < 1e-9
    assert w.confidence.insufficient_below == 55


def test_signal_rules_load():
    r = config.load_signal_rules()
    assert r.version
    assert r.rules == []


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
