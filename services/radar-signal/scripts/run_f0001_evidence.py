"""Run the provenance-bound F-0001 Development measurement and register every outcome."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator, ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from scripts.datapaths import latest_manifest_path, verify_manifest  # noqa: E402
from scripts.fragility_calibration import (  # noqa: E402
    evaluate_fragility_calibration,
    load_fragility_config,
)
from scripts.fragility_event_rows import build_event_row_bundle  # noqa: E402
from scripts.provenance import git_commit, git_is_dirty  # noqa: E402
from scripts.registrylib import latest_manifest_hash, read_all, record_run  # noqa: E402

DEFAULT_OUTPUT = SERVICE_ROOT / "var" / "f0001-evidence.json"
STRATEGY = "F0001FragilityCalibration"
CONTEXT_SET_SCHEMA = SERVICE_ROOT.parents[1] / "contracts" / "f0001-context-set-v1.schema.json"
EXPECTED_EXCLUSIONS = {
    "combined": [],
    "without_funding_stress": ["funding_stress"],
    "without_oi_buildup": ["oi_buildup"],
}


class F0001EvidenceError(ValueError):
    pass


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _load_contexts(path: Path) -> list[dict]:
    paths = (
        sorted(item for item in path.rglob("*.json") if item.name != "context-set.json")
        if path.is_dir()
        else [path]
    )
    if not paths or not all(item.is_file() for item in paths):
        raise F0001EvidenceError(f"decision-context girdisi bulunamadı: {path}")
    contexts = []
    for item in paths:
        payload = json.loads(item.read_text(encoding="utf-8"))
        contexts.extend(payload if isinstance(payload, list) else [payload])
    return contexts


def _load_context_set(path: Path, *, expected_variant: str, config: dict) -> list[dict]:
    manifest_path = path / "context-set.json"
    if not manifest_path.is_file():
        raise F0001EvidenceError(f"context set manifesti yok: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(CONTEXT_SET_SCHEMA.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(manifest)
    except ValidationError as error:
        raise F0001EvidenceError(f"context set sözleşme ihlali: {error.message}") from error
    if manifest.get("schema_version") != "f0001-context-set/v1":
        raise F0001EvidenceError("desteklenmeyen context set şeması")
    if manifest.get("hypothesis_id") != "F-0001" or manifest.get("variant") != expected_variant:
        raise F0001EvidenceError(f"context set variant kimliği uyuşmuyor: {expected_variant}")
    if manifest.get("excluded_features") != EXPECTED_EXCLUSIONS[expected_variant]:
        raise F0001EvidenceError(f"{expected_variant}: excluded_features sözleşmeyle uyuşmuyor")
    if manifest.get("start_utc") != config["boundaries"]["development_start_utc"]:
        raise F0001EvidenceError("context set Development başlangıcı protokolle uyuşmuyor")
    locked = config["boundaries"]["locked_oos_start_utc"]
    boundary_matches = (
        manifest.get("locked_oos_start_utc") == locked
        and manifest.get("end_exclusive_utc") == locked
    )
    if not boundary_matches:
        raise F0001EvidenceError("context set Locked OOS sınırı protokolle uyuşmuyor")
    declared = manifest.get("files", [])
    actual_paths = sorted(item for item in path.rglob("*.json") if item.name != "context-set.json")
    if len(declared) != len(actual_paths) or manifest.get("context_count") != len(actual_paths):
        raise F0001EvidenceError("context set dosya sayısı manifestle uyuşmuyor")
    expected = {entry["file"]: entry["sha256"] for entry in declared}
    actual = {
        str(item.relative_to(path)).replace("\\", "/"): hashlib.sha256(
            item.read_bytes()
        ).hexdigest()
        for item in actual_paths
    }
    if actual != expected:
        raise F0001EvidenceError("context set dosya/hash bütünlüğü bozuk")
    return _load_contexts(path)


def _context_set_sha256(path: Path) -> str:
    return hashlib.sha256((path / "context-set.json").read_bytes()).hexdigest()


def _load_hourly_bars(path: Path) -> list[dict]:
    frame = pd.read_feather(path)
    required = {"date", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise F0001EvidenceError(f"{path.name}: OHLCV kolonları eksik: {missing}")
    dates = pd.to_datetime(frame["date"], utc=True)
    rows = []
    for date, high, low, close in zip(
        dates, frame["high"], frame["low"], frame["close"], strict=True
    ):
        close_at = date.to_pydatetime() + timedelta(hours=1)
        timestamp = close_at.isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "close_at_utc": timestamp,
                "available_at_utc": timestamp,
                "high": float(high),
                "low": float(low),
                "close": float(close),
            }
        )
    return rows


def _manifest_snapshot(manifest_path: Path, required_paths: list[Path]) -> str:
    report = verify_manifest(manifest_path)
    if report["status"] != "ok":
        raise F0001EvidenceError(f"manifest doğrulaması başarısız: {report['status']}")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = {entry["sha256"] for entry in document.get("files", [])}
    for path in required_paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in declared:
            raise F0001EvidenceError(f"girdi güncel manifestte yok: {path}")
    return document["manifest_sha256"]


def build_evidence(
    *,
    contexts: list[dict],
    bars_by_venue: dict[str, list[dict]],
    config: dict,
    dataset_snapshot: str,
    code_sha: str,
    ablation_contexts: dict[str, list[dict]],
    context_set_sha256: dict[str, str],
) -> dict:
    required_ablations = {"without_funding_stress", "without_oi_buildup"}
    if set(ablation_contexts) != required_ablations:
        raise F0001EvidenceError(
            f"zorunlu leave-one-family-out girdileri eksik: {sorted(required_ablations)}"
        )
    required_sets = required_ablations | {"combined"}
    if set(context_set_sha256) != required_sets:
        raise F0001EvidenceError(f"context set manifest hash'leri eksik: {sorted(required_sets)}")
    context_hours = sorted(context["as_of_utc"] for context in contexts)
    for name, ablation_rows in ablation_contexts.items():
        if sorted(context["as_of_utc"] for context in ablation_rows) != context_hours:
            raise F0001EvidenceError(f"{name}: counterfactual karar saatleri ana girdiyle farklı")
    provenance = {
        "dataset_snapshot": dataset_snapshot,
        "code_sha": code_sha,
        "context_set_sha256": context_set_sha256["combined"],
    }
    event_rows = build_event_row_bundle(
        contexts=contexts, bars_by_venue=bars_by_venue, config=config, provenance=provenance
    )
    calibration = evaluate_fragility_calibration(event_rows["rows_by_venue"], config)
    ablations = {}
    for name in sorted(required_ablations):
        bundle = build_event_row_bundle(
            contexts=ablation_contexts[name],
            bars_by_venue=bars_by_venue,
            config=config,
            provenance={
                **provenance,
                "ablation": name,
                "context_set_sha256": context_set_sha256[name],
            },
        )
        ablations[name] = {
            "event_rows_artifact_sha256": bundle["artifact_sha256"],
            "calibration": evaluate_fragility_calibration(bundle["rows_by_venue"], config),
        }
    status = calibration["status"]
    if any(item["calibration"]["status"] == "unavailable" for item in ablations.values()):
        status = "unavailable"
    return {
        "schema_version": "f0001-evidence/v1",
        "hypothesis_id": "F-0001",
        "direction": None,
        "dataset_snapshot": dataset_snapshot,
        "code_sha": code_sha,
        "context_set_sha256": context_set_sha256,
        "status": status,
        "event_rows_artifact_sha256": event_rows["artifact_sha256"],
        "event_row_counts": {
            venue: len(rows) for venue, rows in event_rows["rows_by_venue"].items()
        },
        "venue_coverage": event_rows["venue_coverage"],
        "calibration": calibration,
        "ablations": ablations,
    }


def _registry_verdict(status: str) -> str:
    if status == "passed":
        return "accepted (Development level)"
    if status == "rejected":
        return "rejected (Development gates failed)"
    return "pending (unavailable; data/sample blocker)"


def _record_once(evidence: dict, *, registry_path: Path | None) -> dict:
    existing = [
        row
        for row in read_all(registry_path)
        if row.get("hypothesis_id") == "F-0001"
        and row.get("strategy_version") == evidence["code_sha"]
        and row.get("dataset_snapshot") == evidence["dataset_snapshot"]
        and not str(row.get("verdict", "")).startswith("invalid")
    ]
    if existing:
        return existing[0]
    return record_run(
        registry_path=registry_path,
        hypothesis_id="F-0001",
        strategy=STRATEGY,
        scenario="development_oof",
        effective_fee=0.0,
        exit_code=0,
        verdict=_registry_verdict(evidence["status"]),
        result=evidence,
        pairs=["BTC/USD"],
        created_by="codex",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--contexts-without-funding", type=Path, required=True)
    parser.add_argument("--contexts-without-oi", type=Path, required=True)
    parser.add_argument("--binance-bars", type=Path, required=True)
    parser.add_argument("--coinbase-bars", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args(argv)

    if git_is_dirty():
        raise F0001EvidenceError("kanıt koşusu temiz git çalışma ağacı gerektirir")
    manifest = latest_manifest_path()
    if manifest is None:
        raise F0001EvidenceError("güncel veri manifesti yok")
    snapshot = _manifest_snapshot(manifest, [args.binance_bars, args.coinbase_bars])
    if snapshot != latest_manifest_hash():
        raise F0001EvidenceError("manifest snapshot Registry çözümlemesiyle uyuşmuyor")
    code_sha = git_commit()
    config = load_fragility_config()
    evidence = build_evidence(
        contexts=_load_context_set(args.contexts, expected_variant="combined", config=config),
        bars_by_venue={
            "binance_futures": _load_hourly_bars(args.binance_bars),
            "coinbase_spot": _load_hourly_bars(args.coinbase_bars),
        },
        config=config,
        dataset_snapshot=snapshot,
        code_sha=code_sha,
        ablation_contexts={
            "without_funding_stress": _load_context_set(
                args.contexts_without_funding,
                expected_variant="without_funding_stress",
                config=config,
            ),
            "without_oi_buildup": _load_context_set(
                args.contexts_without_oi,
                expected_variant="without_oi_buildup",
                config=config,
            ),
        },
        context_set_sha256={
            "combined": _context_set_sha256(args.contexts),
            "without_funding_stress": _context_set_sha256(args.contexts_without_funding),
            "without_oi_buildup": _context_set_sha256(args.contexts_without_oi),
        },
    )
    _atomic_json(args.output, evidence)
    entry = _record_once(evidence, registry_path=args.registry)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "artifact": str(args.output),
                "registry_experiment_id": entry["experiment_id"],
                "direction": None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
