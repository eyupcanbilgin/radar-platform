"""Fail-closed F-0001 out-of-fold calibration metrics for prepared event rows."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

import yaml

from scripts.walk_forward_lib import LockedOOSAccessError, generate_walk_forward_plan

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fragility_calibration.yaml"


class FragilityCalibrationError(ValueError):
    pass


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FragilityCalibrationError("timestamp timezone-aware olmalı")
    return parsed.astimezone(UTC)


def load_fragility_config(path: Path | None = None) -> dict:
    data = yaml.safe_load((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    if data.get("version") != "1.1" or data.get("hypothesis_id") != "F-0001":
        raise FragilityCalibrationError("desteklenmeyen F-0001 config kimliği/sürümü")
    if data.get("scope") != "development":
        raise FragilityCalibrationError("F-0001 yalnız development kapsamında çalışır")
    validation = data["validation"]
    if validation.get("required_venues") != ["binance_futures", "coinbase_spot"]:
        raise FragilityCalibrationError("iki dondurulmuş venue birlikte zorunlu")
    if validation.get("probability_estimator") != "laplace_by_trigger_state":
        raise FragilityCalibrationError("olasılık kestiricisi ön-kayıtla uyuşmuyor")
    if validation.get("metric_aggregation") != "pooled_out_of_fold":
        raise FragilityCalibrationError("metrik toplama ön-kayıtla uyuşmuyor")
    alpha = validation.get("laplace_alpha")
    if not isinstance(alpha, int | float) or isinstance(alpha, bool) or alpha <= 0:
        raise FragilityCalibrationError("laplace_alpha pozitif olmalı")
    for key in ("min_event_rate_lift", "min_recall_lift_at_equal_coverage"):
        if float(data["acceptance"].get(key, 0)) <= 0:
            raise FragilityCalibrationError(f"{key} pozitif olmalı")
    return data


def _normalize_rows(rows: list[dict], *, locked_oos: datetime, horizon_hours: int) -> list[dict]:
    normalized = []
    seen = set()
    for raw in rows:
        as_of = _utc(raw["as_of_utc"])
        available = _utc(raw["label_available_at_utc"])
        if as_of >= locked_oos:
            raise LockedOOSAccessError("F-0001 satırı Locked OOS sınırında/sonrasında")
        horizon_end = as_of.timestamp() + horizon_hours * 3600
        if available.timestamp() < horizon_end:
            raise FragilityCalibrationError("etiket available_at dondurulmuş ufuktan önce olamaz")
        if available > locked_oos:
            raise LockedOOSAccessError("F-0001 etiketi Locked OOS verisine erişemez")
        if as_of in seen:
            raise FragilityCalibrationError("aynı venue içinde duplicate as_of")
        seen.add(as_of)
        if not isinstance(raw.get("triggered"), bool) or not isinstance(raw.get("event"), bool):
            raise FragilityCalibrationError("triggered ve event boolean olmalı")
        normalized.append(
            {
                "as_of": as_of,
                "label_available_at": available,
                "triggered": raw["triggered"],
                "event": raw["event"],
            }
        )
    return sorted(normalized, key=lambda row: row["as_of"])


def _laplace(events: int, count: int, alpha: float) -> float:
    return (events + alpha) / (count + 2 * alpha)


def _probability(train: list[dict], triggered: bool, alpha: float) -> float:
    group = [row for row in train if row["triggered"] is triggered]
    return _laplace(sum(row["event"] for row in group), len(group), alpha)


def _venue_report(rows: list[dict], *, config: dict) -> dict:
    validation = config["validation"]
    alpha = float(validation["laplace_alpha"])
    start = _utc(config["boundaries"]["development_start_utc"])
    end = _utc(config["boundaries"]["locked_oos_start_utc"])
    plan = generate_walk_forward_plan(
        start_time=start,
        end_time=end,
        train_window_days=int(validation["train_window_days"]),
        test_window_days=int(validation["test_window_days"]),
        step_days=int(validation["step_days"]),
        embargo_days=int(validation["embargo_days"]),
    )
    predictions = []
    fold_lifts = []
    for fold in plan["folds"]:
        train_start = _utc(fold["train_start_utc"])
        train_end = _utc(fold["train_purged_end_utc"])
        test_start = _utc(fold["test_start_utc"])
        test_end = _utc(fold["test_end_utc"])
        train = [
            row
            for row in rows
            if train_start <= row["as_of"] < train_end and row["label_available_at"] <= train_end
        ]
        test = [row for row in rows if test_start <= row["as_of"] < test_end]
        if not train or not test or not any(row["triggered"] for row in train):
            continue
        base_p = _laplace(sum(row["event"] for row in train), len(train), alpha)
        for row in test:
            predictions.append(
                {
                    **row,
                    "probability": _probability(train, row["triggered"], alpha),
                    "baseline_probability": base_p,
                }
            )
        triggered_test = [row for row in test if row["triggered"]]
        if triggered_test:
            base_rate = sum(row["event"] for row in test) / len(test)
            trigger_rate = sum(row["event"] for row in triggered_test) / len(triggered_test)
            if base_rate > 0:
                fold_lifts.append(trigger_rate / base_rate)
    min_events = int(validation["min_triggered_events_per_venue"])
    triggered = [row for row in predictions if row["triggered"]]
    if len(triggered) < min_events:
        return {
            "status": "unavailable",
            "blockers": [f"insufficient_triggered_events:{len(triggered)}<{min_events}"],
        }
    if not predictions or not any(row["event"] for row in predictions):
        return {"status": "unavailable", "blockers": ["no_out_of_fold_events"]}
    if not fold_lifts:
        return {"status": "unavailable", "blockers": ["no_valid_lift_folds"]}
    event_rate = sum(row["event"] for row in predictions) / len(predictions)
    triggered_rate = sum(row["event"] for row in triggered) / len(triggered)
    event_lift = triggered_rate / event_rate
    positives = sum(row["event"] for row in predictions)
    recall = sum(row["event"] for row in triggered) / positives
    coverage = len(triggered) / len(predictions)
    recall_lift = recall / coverage
    brier = fmean((row["probability"] - row["event"]) ** 2 for row in predictions)
    baseline_brier = fmean((row["baseline_probability"] - row["event"]) ** 2 for row in predictions)
    brier_skill = 1 - brier / baseline_brier if baseline_brier > 0 else -math.inf
    positive_fold_ratio = sum(value > 1 for value in fold_lifts) / len(fold_lifts)
    acceptance = config["acceptance"]
    passed = (
        event_lift >= float(acceptance["min_event_rate_lift"])
        and recall_lift >= float(acceptance["min_recall_lift_at_equal_coverage"])
        and brier_skill > float(acceptance["min_brier_skill_score"])
        and positive_fold_ratio >= float(acceptance["min_positive_fold_ratio"])
    )
    return {
        "status": "passed" if passed else "rejected",
        "blockers": [],
        "out_of_fold_observations": len(predictions),
        "triggered_events": len(triggered),
        "event_rate_lift": event_lift,
        "recall_lift_at_equal_coverage": recall_lift,
        "brier_skill_score": brier_skill,
        "positive_fold_ratio": positive_fold_ratio,
        "valid_folds": len(fold_lifts),
    }


def evaluate_fragility_calibration(rows_by_venue: dict[str, list[dict]], config: dict) -> dict:
    required = config["validation"]["required_venues"]
    missing = [venue for venue in required if venue not in rows_by_venue]
    if missing:
        return {
            "schema_version": "fragility-calibration/v1",
            "status": "unavailable",
            "blockers": [f"missing_venue:{venue}" for venue in missing],
            "venues": {},
        }
    locked_oos = _utc(config["boundaries"]["locked_oos_start_utc"])
    horizon_hours = int(config["outcome"]["horizon_hours"])
    venues = {
        venue: _venue_report(
            _normalize_rows(
                rows_by_venue[venue], locked_oos=locked_oos, horizon_hours=horizon_hours
            ),
            config=config,
        )
        for venue in required
    }
    if any(report["status"] == "unavailable" for report in venues.values()):
        status = "unavailable"
    elif all(report["status"] == "passed" for report in venues.values()):
        status = "passed"
    else:
        status = "rejected"
    return {
        "schema_version": "fragility-calibration/v1",
        "status": status,
        "blockers": [],
        "venues": venues,
        "direction": None,
    }
