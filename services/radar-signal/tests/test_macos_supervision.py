"""Synthetic tests for secret-free macOS paper-runtime LaunchAgents."""

import copy
import hashlib
import plistlib
from pathlib import Path

import pytest
import yaml

from scripts import render_macos_launch_agents as launchd


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    for relative in (
        "services/btc-radar-mcp/btc_radar/producer.py",
        "services/radar-signal/scripts/run_hourly_decision.py",
        "services/radar-signal/scripts/pump.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic\n", encoding="utf-8")
    return root


def _python(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def test_agents_preserve_ordering_direction_null_runtime_and_no_secrets(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    monkeypatch.setattr(launchd, "validate_clean_checkout", lambda path: path.resolve())
    monkeypatch.setattr(
        launchd,
        "validate_state_root",
        lambda path, _: (path.resolve() / "mcp", path.resolve() / "signal"),
    )
    config = launchd.load_supervision_config()
    agents = launchd.build_launch_agents(
        checkout_root=root,
        state_root=tmp_path / "state",
        mcp_python=_python(tmp_path, "mcp-python"),
        signal_python=_python(tmp_path, "signal-python"),
        delivery_mode="console",
        config=config,
    )

    producer = agents["com.radar.mcp-producer"]["ProgramArguments"]
    signal = agents["com.radar.signal-hourly"]["ProgramArguments"]
    pump = agents["com.radar.signal-pump"]
    assert producer[producer.index("--catch-up-hours") + 1] == "0"
    assert int(producer[producer.index("--publish-grace-seconds") + 1]) < int(
        signal[signal.index("--grace-seconds") + 1]
    )
    assert "--f0001-baseline-contexts" in signal
    assert "--f0001-trigger-ledger" in signal
    assert pump["EnvironmentVariables"]["RADAR_SIGNAL_DELIVERY_MODE"] == "console"
    serialized = repr(agents).lower()
    assert "secret" not in serialized
    assert "api_key" not in serialized


def test_config_rejects_signal_before_producer(tmp_path):
    config = copy.deepcopy(launchd.load_supervision_config())
    config["signal"]["decision_grace_seconds"] = config["producer"]["publish_grace_seconds"]
    path = tmp_path / "supervision.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="signal grace"):
        launchd.load_supervision_config(path)


def test_plists_are_atomic_private_and_parseable(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    monkeypatch.setattr(launchd, "validate_clean_checkout", lambda path: path.resolve())
    monkeypatch.setattr(
        launchd,
        "validate_state_root",
        lambda path, _: (path.resolve() / "mcp", path.resolve() / "signal"),
    )
    agents = launchd.build_launch_agents(
        checkout_root=root,
        state_root=tmp_path / "state",
        mcp_python=_python(tmp_path, "mcp-python"),
        signal_python=_python(tmp_path, "signal-python"),
        delivery_mode="telegram",
        config=launchd.load_supervision_config(),
    )
    written = launchd.write_launch_agents(tmp_path / "agents", agents)

    assert len(written) == 3
    for path in written:
        assert path.stat().st_mode & 0o777 == 0o600
        payload = plistlib.loads(path.read_bytes())
        assert payload["KeepAlive"] is True
        assert payload["RunAtLoad"] is True
        assert Path(payload["StandardOutPath"]).parent.is_dir()


def test_state_root_requires_the_configured_baseline_hash(tmp_path):
    manifest = tmp_path / "state/signal/f0001-contexts/combined/context-set.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b'{"synthetic":true}\n')
    signal_root = tmp_path / "signal-service"
    config_path = signal_root / "config/f0001_forward_observation.yaml"
    config_path.parent.mkdir(parents=True)
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    config_path.write_text(f'baseline_context_set_sha256: "{expected}"\n', encoding="utf-8")

    mcp_state, signal_state = launchd.validate_state_root(tmp_path / "state", signal_root)
    assert mcp_state == (tmp_path / "state/mcp").resolve()
    assert signal_state == (tmp_path / "state/signal").resolve()

    config_path.write_text(f'baseline_context_set_sha256: "{"0" * 64}"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="baseline hash uyuşmuyor"):
        launchd.validate_state_root(tmp_path / "state", signal_root)
