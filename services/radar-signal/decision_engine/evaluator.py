"""Service for evaluating +1h, +4h, and +24h outcomes of DecisionCards."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml

from decision_engine.canonical import sha256_hex
from decision_engine.decision import DecisionCardV1
from decision_engine.features import Candle1h
from decision_engine.ledger import DecisionLedger
from decision_engine.outcomes import (
    EVALUATOR_VERSION,
    HORIZON_MAP,
    DecisionOutcomeV1,
    OutcomeDataHealthV1,
    compute_outcome_id,
)
from decision_engine.runtime import ClosedCandleSource


def load_cost_config(config_path: Path | str | None = None) -> dict | None:
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "costs.yaml"
    path = Path(config_path)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def calculate_net_cost(
    cost_config: dict | None,
    symbol: str = "BTCUSDT",
) -> float | None:
    if not cost_config or not isinstance(cost_config, dict):
        return None
    fees = cost_config.get("fees", {})
    slippage = cost_config.get("slippage_oneway", {})
    taker_fee = fees.get("taker")
    one_way_slip = slippage.get(symbol)
    if taker_fee is None or one_way_slip is None:
        return None
    try:
        taker_fee = float(taker_fee)
        one_way_slip = float(one_way_slip)
    except (TypeError, ValueError):
        return None

    # Roundtrip fee (entry taker + exit taker) + roundtrip slippage (entry slip + exit slip)
    return round(2.0 * taker_fee + 2.0 * one_way_slip, 8)


def evaluate_horizon_outcome(
    decision: DecisionCardV1,
    horizon: Literal["+1h", "+4h", "+24h"],
    candles: list[Candle1h],
    *,
    evaluation_time_utc: datetime,
    cost_config: dict | None = None,
    close_grace_seconds: int = 90,
) -> DecisionOutcomeV1:
    if evaluation_time_utc.tzinfo is None:
        raise ValueError("evaluation_time_utc timezone-aware UTC olmalı")
    evaluation_time_utc = evaluation_time_utc.astimezone(UTC)

    as_of = decision.as_of_utc
    expected_hours = HORIZON_MAP[horizon]
    horizon_close = as_of + timedelta(hours=expected_hours)
    ready_at = horizon_close + timedelta(seconds=close_grace_seconds)

    outcome_id = compute_outcome_id(
        decision_id=decision.decision_id,
        horizon=horizon,
        evaluator_version=EVALUATOR_VERSION,
    )

    if evaluation_time_utc < ready_at:
        health = OutcomeDataHealthV1(
            ready=False,
            missing_reasons=["horizon_not_expired"],
            candle_count=0,
            expected_candle_count=expected_hours,
        )
        body = {
            "schema_version": "decision-outcome/v1",
            "outcome_id": outcome_id,
            "decision_id": decision.decision_id,
            "instrument": decision.instrument.model_dump(mode="json"),
            "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
            "horizon": horizon,
            "horizon_close_utc": horizon_close.isoformat().replace("+00:00", "Z"),
            "decision_outcome": decision.outcome,
            "status": "pending",
            "reference_price": None,
            "horizon_close_price": None,
            "raw_return": None,
            "net_return": None,
            "mfe": None,
            "mae": None,
            "opportunity_return": None,
            "data_health": health.model_dump(mode="json"),
            "evaluator_version": EVALUATOR_VERSION,
        }
        content_hash = sha256_hex(body)
        return DecisionOutcomeV1(
            outcome_id=outcome_id,
            decision_id=decision.decision_id,
            instrument=decision.instrument,
            as_of_utc=as_of,
            horizon=horizon,
            horizon_close_utc=horizon_close,
            decision_outcome=decision.outcome,
            status="pending",
            data_health=health,
            evaluator_version=EVALUATOR_VERSION,
            content_hash=content_hash,
        )

    # Filter candles strictly in the window [as_of, horizon_close]
    eligible = [
        c
        for c in candles
        if c.open_time_utc >= as_of
        and c.close_time_utc <= horizon_close
        and c.available_at_utc <= horizon_close
    ]
    eligible.sort(key=lambda c: c.open_time_utc)

    missing_reasons: list[str] = []
    if not eligible:
        missing_reasons.append("missing_horizon_candles")
    else:
        if len(eligible) < expected_hours:
            missing_reasons.append(f"incomplete_horizon_{expected_hours}h")
        if eligible[0].open_time_utc != as_of:
            missing_reasons.append("missing_reference_candle")
        if eligible[-1].close_time_utc != horizon_close:
            missing_reasons.append("missing_horizon_close_candle")
        contiguous = all(
            right.open_time_utc - left.open_time_utc == timedelta(hours=1)
            for left, right in zip(eligible, eligible[1:], strict=False)
        )
        if not contiguous:
            missing_reasons.append("horizon_gap_detected")

    missing_reasons = sorted(set(missing_reasons))

    if missing_reasons:
        candle_digest = (
            sha256_hex([c.model_dump(mode="json") for c in eligible]) if eligible else None
        )
        health = OutcomeDataHealthV1(
            ready=False,
            missing_reasons=missing_reasons,
            candle_count=len(eligible),
            expected_candle_count=expected_hours,
            first_candle_open_utc=eligible[0].open_time_utc if eligible else None,
            last_candle_close_utc=eligible[-1].close_time_utc if eligible else None,
            candle_digest=candle_digest,
        )
        body = {
            "schema_version": "decision-outcome/v1",
            "outcome_id": outcome_id,
            "decision_id": decision.decision_id,
            "instrument": decision.instrument.model_dump(mode="json"),
            "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
            "horizon": horizon,
            "horizon_close_utc": horizon_close.isoformat().replace("+00:00", "Z"),
            "decision_outcome": decision.outcome,
            "status": "unavailable",
            "reference_price": None,
            "horizon_close_price": None,
            "raw_return": None,
            "net_return": None,
            "mfe": None,
            "mae": None,
            "opportunity_return": None,
            "data_health": health.model_dump(mode="json"),
            "evaluator_version": EVALUATOR_VERSION,
        }
        content_hash = sha256_hex(body)
        return DecisionOutcomeV1(
            outcome_id=outcome_id,
            decision_id=decision.decision_id,
            instrument=decision.instrument,
            as_of_utc=as_of,
            horizon=horizon,
            horizon_close_utc=horizon_close,
            decision_outcome=decision.outcome,
            status="unavailable",
            data_health=health,
            evaluator_version=EVALUATOR_VERSION,
            content_hash=content_hash,
        )

    # Validated continuous window of closed candles
    ref_price = eligible[0].open
    close_price = eligible[-1].close
    high_max = max(c.high for c in eligible)
    low_min = min(c.low for c in eligible)
    candle_digest = sha256_hex([c.model_dump(mode="json") for c in eligible])

    health = OutcomeDataHealthV1(
        ready=True,
        missing_reasons=[],
        candle_count=len(eligible),
        expected_candle_count=expected_hours,
        first_candle_open_utc=eligible[0].open_time_utc,
        last_candle_close_utc=eligible[-1].close_time_utc,
        candle_digest=candle_digest,
    )

    cost = calculate_net_cost(cost_config, symbol=decision.instrument.symbol)

    if decision.outcome == "LONG":
        raw_ret = round((close_price - ref_price) / ref_price, 12)
        mfe_val = round((high_max - ref_price) / ref_price, 12)
        mae_val = round((low_min - ref_price) / ref_price, 12)
        opp_ret = None
        net_ret = round(raw_ret - cost, 12) if cost is not None else None
    elif decision.outcome == "SHORT":
        raw_ret = round((ref_price - close_price) / ref_price, 12)
        mfe_val = round((ref_price - low_min) / ref_price, 12)
        mae_val = round((ref_price - high_max) / ref_price, 12)
        opp_ret = None
        net_ret = round(raw_ret - cost, 12) if cost is not None else None
    else:  # WAIT
        raw_ret = None
        mfe_val = None
        mae_val = None
        net_ret = None
        opp_ret = round((close_price - ref_price) / ref_price, 12)

    body = {
        "schema_version": "decision-outcome/v1",
        "outcome_id": outcome_id,
        "decision_id": decision.decision_id,
        "instrument": decision.instrument.model_dump(mode="json"),
        "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
        "horizon": horizon,
        "horizon_close_utc": horizon_close.isoformat().replace("+00:00", "Z"),
        "decision_outcome": decision.outcome,
        "status": "evaluated",
        "reference_price": ref_price,
        "horizon_close_price": close_price,
        "raw_return": raw_ret,
        "net_return": net_ret,
        "mfe": mfe_val,
        "mae": mae_val,
        "opportunity_return": opp_ret,
        "data_health": health.model_dump(mode="json"),
        "evaluator_version": EVALUATOR_VERSION,
    }
    content_hash = sha256_hex(body)

    return DecisionOutcomeV1(
        outcome_id=outcome_id,
        decision_id=decision.decision_id,
        instrument=decision.instrument,
        as_of_utc=as_of,
        horizon=horizon,
        horizon_close_utc=horizon_close,
        decision_outcome=decision.outcome,
        status="evaluated",
        reference_price=ref_price,
        horizon_close_price=close_price,
        raw_return=raw_ret,
        net_return=net_ret,
        mfe=mfe_val,
        mae=mae_val,
        opportunity_return=opp_ret,
        data_health=health,
        evaluator_version=EVALUATOR_VERSION,
        content_hash=content_hash,
    )


class HourlyOutcomeEvaluator:
    """Orchestrates fetching market candles and saving decision outcomes to the ledger."""

    def __init__(
        self,
        ledger: DecisionLedger,
        candle_source: ClosedCandleSource,
        *,
        cost_config: dict | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.ledger = ledger
        self.candle_source = candle_source
        self.cost_config = cost_config or load_cost_config()
        self.clock = clock or (lambda: datetime.now(UTC))

    def evaluate_decision(
        self,
        decision_id: str,
        *,
        horizons: tuple[Literal["+1h", "+4h", "+24h"], ...] = ("+1h", "+4h", "+24h"),
    ) -> list[DecisionOutcomeV1]:
        record = self.ledger.get(decision_id)
        if not record:
            raise ValueError(f"karar ledger'da bulunamadı: {decision_id}")

        decision = DecisionCardV1.model_validate(record["decision_payload"])
        now = self.clock()

        max_horizon_hours = max(HORIZON_MAP[h] for h in horizons)
        end_fetch = decision.as_of_utc + timedelta(hours=max_horizon_hours)

        try:
            batch = self.candle_source.fetch_closed(as_of_utc=end_fetch)
            candles = list(batch.candles)
        except Exception:
            candles = []

        outcomes = []
        for horizon in horizons:
            outcome = evaluate_horizon_outcome(
                decision=decision,
                horizon=horizon,
                candles=candles,
                evaluation_time_utc=now,
                cost_config=self.cost_config,
            )
            self.ledger.record_outcome(outcome, recorded_at_utc=now)
            outcomes.append(outcome)
        return outcomes
