"""Deterministic historical F-0001 context sets with sealed variant manifests."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from btc_radar.core.context_producer import produce_context
from btc_radar.core.context_publisher import ExactHourContextPublisher, require_utc_hour
from btc_radar.core.snapshot import SnapshotStore
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import SignalRulesConfig

VARIANT_EXCLUSIONS = {
    "combined": frozenset(),
    "without_funding_stress": frozenset({"funding_stress"}),
    "without_oi_buildup": frozenset({"oi_buildup"}),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object_sha256(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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


def _variant_rules(rules: SignalRulesConfig, excluded: frozenset[str]) -> SignalRulesConfig:
    return rules.model_copy(
        update={"rules": [rule for rule in rules.rules if rule.feature not in excluded]}
    )


def generate_f0001_context_sets(
    *,
    start_utc: datetime,
    end_exclusive_utc: datetime,
    locked_oos_start_utc: datetime,
    pit_store: PointInTimeStore,
    snapshot_root: Path,
    output_root: Path,
    rules: SignalRulesConfig,
) -> dict:
    start = require_utc_hour(start_utc)
    end = require_utc_hour(end_exclusive_utc)
    locked = require_utc_hour(locked_oos_start_utc)
    if end <= start:
        raise ValueError("context set end başlangıçtan sonra olmalı")
    if end > locked:
        raise ValueError("F-0001 context set Locked OOS sınırını açamaz")

    variants = {}
    for variant, exclusions in VARIANT_EXCLUSIONS.items():
        variant_root = output_root / variant
        publisher = ExactHourContextPublisher(variant_root)
        variant_rules = _variant_rules(rules, exclusions)
        cursor = start
        files = []
        unavailable = 0
        with SnapshotStore(snapshot_root / f"{variant}.sqlite") as snapshot_store:
            while cursor < end:
                result = produce_context(
                    as_of_utc=cursor,
                    pit_store=pit_store,
                    snapshot_store=snapshot_store,
                    publisher=publisher,
                    computed_at_utc=end,
                    rules=variant_rules,
                )
                path = result.publication.path
                files.append(
                    {
                        "file": str(path.relative_to(variant_root)).replace("\\", "/"),
                        "sha256": _sha256(path),
                    }
                )
                if result.snapshot.fragility is None:
                    unavailable += 1
                cursor += timedelta(hours=1)
        manifest = {
            "schema_version": "f0001-context-set/v1",
            "hypothesis_id": "F-0001",
            "variant": variant,
            "excluded_features": sorted(exclusions),
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_exclusive_utc": end.isoformat().replace("+00:00", "Z"),
            "locked_oos_start_utc": locked.isoformat().replace("+00:00", "Z"),
            "rules_version": rules.version,
            "rules_sha256": _object_sha256(rules.model_dump(mode="json")),
            "context_count": len(files),
            "unavailable_count": unavailable,
            "files": files,
        }
        _atomic_json(variant_root / "context-set.json", manifest)
        variants[variant] = {
            "context_count": len(files),
            "unavailable_count": unavailable,
            "manifest": str((variant_root / "context-set.json").resolve()),
        }
    return {
        "schema_version": "f0001-context-backfill/v1",
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "end_exclusive_utc": end.isoformat().replace("+00:00", "Z"),
        "direction": None,
        "variants": variants,
    }
