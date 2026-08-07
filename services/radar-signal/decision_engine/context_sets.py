"""Lightweight F-0001 context-set contract and integrity loader."""

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_SET_SCHEMA = SERVICE_ROOT.parents[1] / "contracts/f0001-context-set-v1.schema.json"
EXPECTED_EXCLUSIONS = {
    "combined": [],
    "without_funding_stress": ["funding_stress"],
    "without_oi_buildup": ["oi_buildup"],
}


class ContextSetError(ValueError):
    pass


def load_contexts(path: Path) -> list[dict]:
    paths = (
        sorted(item for item in path.rglob("*.json") if item.name != "context-set.json")
        if path.is_dir()
        else [path]
    )
    if not paths or not all(item.is_file() for item in paths):
        raise ContextSetError(f"decision-context girdisi bulunamadı: {path}")
    contexts = []
    for item in paths:
        payload = json.loads(item.read_text(encoding="utf-8"))
        contexts.extend(payload if isinstance(payload, list) else [payload])
    return contexts


def load_context_set(path: Path, *, expected_variant: str, config: dict) -> list[dict]:
    if expected_variant not in EXPECTED_EXCLUSIONS:
        raise ContextSetError(f"desteklenmeyen context set variantı: {expected_variant}")
    manifest_path = path / "context-set.json"
    if not manifest_path.is_file():
        raise ContextSetError(f"context set manifesti yok: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(CONTEXT_SET_SCHEMA.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(manifest)
    except ValidationError as error:
        raise ContextSetError(f"context set sözleşme ihlali: {error.message}") from error
    if manifest.get("schema_version") != "f0001-context-set/v1":
        raise ContextSetError("desteklenmeyen context set şeması")
    if manifest.get("hypothesis_id") != "F-0001" or manifest.get("variant") != expected_variant:
        raise ContextSetError(f"context set variant kimliği uyuşmuyor: {expected_variant}")
    if manifest.get("excluded_features") != EXPECTED_EXCLUSIONS[expected_variant]:
        raise ContextSetError(f"{expected_variant}: excluded_features sözleşmeyle uyuşmuyor")
    if manifest.get("start_utc") != config["boundaries"]["development_start_utc"]:
        raise ContextSetError("context set Development başlangıcı protokolle uyuşmuyor")
    locked = config["boundaries"]["locked_oos_start_utc"]
    if not (
        manifest.get("locked_oos_start_utc") == locked
        and manifest.get("end_exclusive_utc") == locked
    ):
        raise ContextSetError("context set Locked OOS sınırı protokolle uyuşmuyor")
    declared = manifest.get("files", [])
    actual_paths = sorted(item for item in path.rglob("*.json") if item.name != "context-set.json")
    if len(declared) != len(actual_paths) or manifest.get("context_count") != len(actual_paths):
        raise ContextSetError("context set dosya sayısı manifestle uyuşmuyor")
    expected = {entry["file"]: entry["sha256"] for entry in declared}
    actual = {
        str(item.relative_to(path)).replace("\\", "/"): hashlib.sha256(
            item.read_bytes()
        ).hexdigest()
        for item in actual_paths
    }
    if actual != expected:
        raise ContextSetError("context set dosya/hash bütünlüğü bozuk")
    return load_contexts(path)


def context_set_sha256(path: Path) -> str:
    manifest_path = path / "context-set.json"
    if not manifest_path.is_file():
        raise ContextSetError(f"context set manifesti yok: {manifest_path}")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()
