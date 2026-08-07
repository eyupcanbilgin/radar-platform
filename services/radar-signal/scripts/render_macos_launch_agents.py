"""Render secret-free launchd agents for the local paper runtime; never installs them."""

import argparse
import hashlib
import os
import plistlib
import subprocess
import tempfile
from pathlib import Path

import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
DEFAULT_CONFIG = SERVICE_ROOT / "config" / "macos_supervision.yaml"


def load_supervision_config(path: Path = DEFAULT_CONFIG) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("version") != "1":
        raise ValueError("macOS supervision config version=1 olmalı")
    producer = config["producer"]
    signal = config["signal"]
    pump = config["pump"]
    launchd = config["launchd"]
    for field, value in (
        ("producer.collect_interval_seconds", producer["collect_interval_seconds"]),
        ("producer.publish_grace_seconds", producer["publish_grace_seconds"]),
        ("producer.history_limit", producer["history_limit"]),
        ("signal.decision_grace_seconds", signal["decision_grace_seconds"]),
        ("pump.interval_seconds", pump["interval_seconds"]),
        ("launchd.throttle_interval_seconds", launchd["throttle_interval_seconds"]),
    ):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} negatif olmayan integer olmalı")
    if producer["collect_interval_seconds"] == 0 or pump["interval_seconds"] == 0:
        raise ValueError("collect/pump interval sıfır olamaz")
    producer_grace = producer["publish_grace_seconds"]
    decision_grace = signal["decision_grace_seconds"]
    if not producer_grace < decision_grace < 3600:
        raise ValueError("signal grace, producer grace'ten büyük ve 3600'den küçük olmalı")
    if launchd["throttle_interval_seconds"] == 0:
        raise ValueError("launchd throttle sıfır olamaz")
    return config


def _require_file(path: Path, description: str, *, executable: bool = False) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{description} bulunamadı: {resolved}")
    if executable and not os.access(resolved, os.X_OK):
        raise ValueError(f"{description} çalıştırılabilir değil: {resolved}")
    return resolved


def validate_clean_checkout(checkout_root: Path) -> Path:
    root = checkout_root.expanduser().resolve()
    _require_file(root / "services/btc-radar-mcp/btc_radar/producer.py", "MCP producer")
    _require_file(root / "services/radar-signal/scripts/run_hourly_decision.py", "Signal runtime")
    _require_file(root / "services/radar-signal/scripts/pump.py", "Signal pump")
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise ValueError("launchd checkout kirli; paper provenance için temiz checkout zorunlu")
    return root


def validate_state_root(state_root: Path, signal_root: Path) -> tuple[Path, Path]:
    state = state_root.expanduser().resolve()
    mcp_state = state / "mcp"
    signal_state = state / "signal"
    baseline_manifest = signal_state / "f0001-contexts/combined/context-set.json"
    if not baseline_manifest.is_file():
        raise FileNotFoundError(f"mühürlü combined baseline bulunamadı: {baseline_manifest}")
    observation_config = yaml.safe_load(
        (signal_root / "config/f0001_forward_observation.yaml").read_text(encoding="utf-8")
    )
    actual_hash = hashlib.sha256(baseline_manifest.read_bytes()).hexdigest()
    expected_hash = observation_config["baseline_context_set_sha256"]
    if actual_hash != expected_hash:
        raise ValueError(
            f"combined baseline hash uyuşmuyor: beklenen={expected_hash}, gelen={actual_hash}"
        )
    mcp_state.mkdir(parents=True, exist_ok=True)
    signal_state.mkdir(parents=True, exist_ok=True)
    return mcp_state, signal_state


def _agent(
    *,
    label: str,
    arguments: list[str],
    working_directory: Path,
    log_root: Path,
    throttle_seconds: int,
    environment: dict[str, str] | None = None,
) -> dict:
    payload = {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(working_directory),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": throttle_seconds,
        "StandardOutPath": str(log_root / f"{label}.stdout.log"),
        "StandardErrorPath": str(log_root / f"{label}.stderr.log"),
    }
    if environment:
        payload["EnvironmentVariables"] = environment
    return payload


def build_launch_agents(
    *,
    checkout_root: Path,
    state_root: Path,
    mcp_python: Path,
    signal_python: Path,
    delivery_mode: str,
    config: dict,
) -> dict[str, dict]:
    if delivery_mode not in {"console", "telegram"}:
        raise ValueError("delivery mode console veya telegram olmalı")
    root = validate_clean_checkout(checkout_root)
    mcp_python = _require_file(mcp_python, "MCP Python", executable=True)
    signal_python = _require_file(signal_python, "Signal Python", executable=True)
    mcp_root = root / "services/btc-radar-mcp"
    signal_root = root / "services/radar-signal"
    mcp_var, signal_var = validate_state_root(state_root, signal_root)
    log_root = signal_var / "logs"
    producer = config["producer"]
    signal = config["signal"]
    throttle = config["launchd"]["throttle_interval_seconds"]

    return {
        "com.radar.mcp-producer": _agent(
            label="com.radar.mcp-producer",
            arguments=[
                str(mcp_python),
                "-m",
                "btc_radar.producer",
                "run",
                "--daemon",
                "--pit-db",
                str(mcp_var / "pit.sqlite"),
                "--snapshot-db",
                str(mcp_var / "snapshots.sqlite"),
                "--context-root",
                str(signal_var / "decision-context"),
                "--heartbeat-db",
                str(mcp_var / "heartbeat.sqlite"),
                "--lock-file",
                str(mcp_var / "producer.lock"),
                "--collect-interval-seconds",
                str(producer["collect_interval_seconds"]),
                "--publish-grace-seconds",
                str(producer["publish_grace_seconds"]),
                "--history-limit",
                str(producer["history_limit"]),
                "--catch-up-hours",
                "0",
            ],
            working_directory=mcp_root,
            log_root=log_root,
            throttle_seconds=throttle,
        ),
        "com.radar.signal-hourly": _agent(
            label="com.radar.signal-hourly",
            arguments=[
                str(signal_python),
                str(signal_root / "scripts/run_hourly_decision.py"),
                "--daemon",
                "--ledger",
                str(signal_var / "hourly-decisions.sqlite"),
                "--outbox",
                str(signal_var / "outbox.sqlite"),
                "--context-dir",
                str(signal_var / "decision-context"),
                "--grace-seconds",
                str(signal["decision_grace_seconds"]),
                "--f0001-baseline-contexts",
                str(signal_var / "f0001-contexts/combined"),
                "--f0001-trigger-ledger",
                str(signal_var / "f0001-forward-triggers.sqlite"),
            ],
            working_directory=signal_root,
            log_root=log_root,
            throttle_seconds=throttle,
        ),
        "com.radar.signal-pump": _agent(
            label="com.radar.signal-pump",
            arguments=[
                str(signal_python),
                str(signal_root / "scripts/pump.py"),
                "--interval",
                str(config["pump"]["interval_seconds"]),
            ],
            working_directory=signal_root,
            log_root=log_root,
            throttle_seconds=throttle,
            environment={
                "RADAR_SIGNAL_DB_DIR": str(signal_var),
                "RADAR_SIGNAL_DELIVERY_MODE": delivery_mode,
            },
        ),
    }


def write_launch_agents(output_dir: Path, agents: dict[str, dict]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_root = Path(next(iter(agents.values()))["StandardOutPath"]).parent
    log_root.mkdir(parents=True, exist_ok=True)
    written = []
    for label, payload in sorted(agents.items()):
        destination = output_dir / f"{label}.plist"
        data = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
        with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        written.append(destination)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--mcp-python", type=Path, required=True)
    parser.add_argument("--signal-python", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--delivery-mode", choices=("console", "telegram"), default="console")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    agents = build_launch_agents(
        checkout_root=args.checkout_root,
        state_root=args.state_root,
        mcp_python=args.mcp_python,
        signal_python=args.signal_python,
        delivery_mode=args.delivery_mode,
        config=load_supervision_config(args.config),
    )
    written = write_launch_agents(args.output_dir.expanduser().resolve(), agents)
    print("\n".join(str(path) for path in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
