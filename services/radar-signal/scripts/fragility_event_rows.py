"""Build PIT-safe F-0001 trigger/outcome rows from contexts and hourly venue bars."""

import hashlib
import json
import math
from datetime import datetime, timedelta

from scripts.fragility_calibration import FragilityCalibrationError, _utc


def _hash(value: object) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def _midrank(values: list[float], value: float) -> float:
    if not values:
        raise FragilityCalibrationError("midrank dağılımı boş")
    below = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return 100 * (below + equal / 2) / len(values)


def build_trigger_rows(contexts: list[dict], config: dict) -> list[dict]:
    cfg = config["trigger"]
    lookback = timedelta(days=int(cfg["rolling_lookback_days"]))
    minimum_span = timedelta(days=int(cfg["min_history_days"]))
    cooldown = timedelta(hours=int(cfg["episode_cooldown_hours"]))
    observations = []
    seen = set()
    for context in contexts:
        as_of = _utc(context["as_of_utc"])
        cutoff = _utc(context["data_cutoff_at_utc"])
        snapshot = context["snapshot"]
        gates = context["gates"]
        if cutoff > as_of:
            raise FragilityCalibrationError("context look-ahead: data_cutoff > as_of")
        if snapshot.get("direction") is not None or gates.get("directional_decision_allowed"):
            raise FragilityCalibrationError("F-0001 context direction-null/kapalı olmalı")
        if as_of in seen:
            raise FragilityCalibrationError("duplicate context as_of")
        seen.add(as_of)
        value = snapshot.get("fragility")
        if value is None:
            continue
        value = float(value)
        if not math.isfinite(value):
            raise FragilityCalibrationError("fragility sonlu olmalı")
        observations.append({"as_of": as_of, "fragility": value})
    observations.sort(key=lambda row: row["as_of"])
    result = []
    last_trigger = None
    for row in observations:
        history = [
            item
            for item in observations
            if row["as_of"] - lookback <= item["as_of"] <= row["as_of"]
        ]
        if len(history) < int(cfg["min_observations"]):
            continue
        if history[-1]["as_of"] - history[0]["as_of"] < minimum_span:
            continue
        percentile = _midrank([item["fragility"] for item in history], row["fragility"])
        high = percentile >= float(cfg["percentile_threshold"])
        if high and last_trigger is not None and row["as_of"] < last_trigger + cooldown:
            continue
        triggered = bool(high)
        if triggered:
            last_trigger = row["as_of"]
        result.append({"as_of": row["as_of"], "triggered": triggered, "percentile": percentile})
    return result


def build_venue_labels(bars: list[dict], config: dict) -> dict[datetime, dict]:
    cfg = config["outcome"]
    horizon = int(cfg["horizon_hours"])
    trailing = int(cfg["trailing_volatility_hours"])
    parsed = []
    for raw in bars:
        close_at = _utc(raw["close_at_utc"])
        available = _utc(raw["available_at_utc"])
        if available < close_at:
            raise FragilityCalibrationError("bar available_at close_at öncesinde")
        parsed.append({**raw, "close_at": close_at, "available_at": available})
    parsed.sort(key=lambda row: row["close_at"])
    if not parsed:
        raise FragilityCalibrationError("venue OHLCV boş")
    if len({row["close_at"] for row in parsed}) != len(parsed):
        raise FragilityCalibrationError("duplicate venue bar")
    segments = [[parsed[0]]]
    for left, right in zip(parsed, parsed[1:], strict=False):
        delta = right["close_at"] - left["close_at"]
        if delta == timedelta(hours=1):
            segments[-1].append(right)
            continue
        if delta <= timedelta(0) or delta % timedelta(hours=1):
            raise FragilityCalibrationError("venue OHLCV gap tam saat katı olmalı")
        segments.append([right])
    ratios = []
    by_time = {}
    for segment in segments:
        for index in range(trailing, len(segment) - horizon):
            current = segment[index]
            as_of = current["close_at"]
            before = segment[index - trailing : index + 1]
            after = segment[index : index + horizon + 1]
            trailing_returns = [
                math.log(before[i]["close"] / before[i - 1]["close"]) for i in range(1, len(before))
            ]
            forward_returns = [
                math.log(after[i]["close"] / after[i - 1]["close"]) for i in range(1, len(after))
            ]
            trailing_rv = math.sqrt(sum(value * value for value in trailing_returns))
            forward_rv = math.sqrt(sum(value * value for value in forward_returns))
            if trailing_rv == 0:
                continue
            ratio = forward_rv / trailing_rv
            settled = [
                item
                for item in ratios
                if item["available_at"] <= as_of
                and item["as_of"]
                >= as_of - timedelta(days=int(cfg["label_distribution_lookback_days"]))
            ]
            if len(settled) >= int(cfg["min_settled_labels"]):
                percentile = _midrank([item["ratio"] for item in settled], ratio)
                reference = float(current["close"])
                excursion = max(
                    max(
                        abs(float(item["high"]) / reference - 1),
                        abs(float(item["low"]) / reference - 1),
                    )
                    for item in after[1:]
                )
                by_time[as_of] = {
                    "event": percentile >= float(cfg["expansion_percentile_threshold"]),
                    "label_available_at": after[-1]["available_at"],
                    "volatility_expansion_ratio": ratio,
                    "max_absolute_excursion": excursion,
                }
            ratios.append(
                {"as_of": as_of, "available_at": after[-1]["available_at"], "ratio": ratio}
            )
    return by_time


def venue_coverage(bars: list[dict]) -> dict:
    times = sorted(_utc(row["close_at_utc"]) for row in bars)
    gaps = []
    for left, right in zip(times, times[1:], strict=False):
        if right - left > timedelta(hours=1):
            gaps.append(
                {
                    "after_utc": left.isoformat().replace("+00:00", "Z"),
                    "before_utc": right.isoformat().replace("+00:00", "Z"),
                    "missing_hours": int((right - left) / timedelta(hours=1)) - 1,
                }
            )
    return {
        "observed_hours": len(times),
        "missing_hours": sum(item["missing_hours"] for item in gaps),
        "segment_count": len(gaps) + 1 if times else 0,
        "gaps": gaps,
    }


def build_event_row_bundle(
    *, contexts: list[dict], bars_by_venue: dict[str, list[dict]], config: dict, provenance: dict
) -> dict:
    required = config["validation"]["required_venues"]
    missing = [venue for venue in required if venue not in bars_by_venue]
    if missing:
        raise FragilityCalibrationError(f"venue OHLCV eksik: {missing}")
    triggers = build_trigger_rows(contexts, config)
    rows_by_venue = {}
    for venue in required:
        labels = build_venue_labels(bars_by_venue[venue], config)
        rows_by_venue[venue] = [
            {
                "as_of_utc": row["as_of"].isoformat().replace("+00:00", "Z"),
                "label_available_at_utc": labels[row["as_of"]]["label_available_at"]
                .isoformat()
                .replace("+00:00", "Z"),
                "triggered": row["triggered"],
                "event": labels[row["as_of"]]["event"],
                "trigger_percentile": row["percentile"],
                "volatility_expansion_ratio": labels[row["as_of"]]["volatility_expansion_ratio"],
                "max_absolute_excursion": labels[row["as_of"]]["max_absolute_excursion"],
            }
            for row in triggers
            if row["as_of"] in labels
        ]
    hashes = {
        "contexts_sha256": _hash(contexts),
        "venues_sha256": {venue: _hash(bars_by_venue[venue]) for venue in required},
        "config_sha256": _hash(config),
        **provenance,
    }
    payload = {
        "schema_version": "fragility-event-rows/v1",
        "hypothesis_id": "F-0001",
        "direction": None,
        "provenance": hashes,
        "rows_by_venue": rows_by_venue,
        "venue_coverage": {venue: venue_coverage(bars_by_venue[venue]) for venue in required},
    }
    payload["artifact_sha256"] = _hash(payload)
    return payload
