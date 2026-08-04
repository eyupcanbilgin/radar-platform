"""Single-call hourly evaluation: FeatureSnapshot -> DecisionCard -> immutable ledger."""

from dataclasses import dataclass
from datetime import datetime

from decision_engine.decision import DecisionCardV1, DirectionalSetup, build_hourly_decision
from decision_engine.features import Candle1h, FeatureSnapshotV1, build_feature_snapshot
from decision_engine.ledger import DecisionLedger
from enricher.decision_context import DecisionContextV1


@dataclass(frozen=True)
class RecordedDecision:
    feature: FeatureSnapshotV1
    decision: DecisionCardV1
    created: bool


class HourlyDecisionService:
    def __init__(self, ledger: DecisionLedger, *, signal_commit: str):
        self.ledger = ledger
        self.signal_commit = signal_commit

    def evaluate_and_record(
        self,
        *,
        candles: list[Candle1h],
        context: DecisionContextV1 | None,
        as_of_utc: datetime | None = None,
        setup: DirectionalSetup | None = None,
        recorded_at_utc: datetime | None = None,
    ) -> RecordedDecision:
        if context is not None:
            decision_time = context.as_of_utc
        elif as_of_utc is not None:
            decision_time = as_of_utc
        else:
            raise ValueError("context yokken as_of_utc zorunlu")
        feature = build_feature_snapshot(candles, as_of=decision_time)
        decision = build_hourly_decision(
            feature,
            context,
            setup=setup,
            signal_commit=self.signal_commit,
        )
        created = self.ledger.record(
            feature=feature,
            context=context,
            decision=decision,
            recorded_at_utc=recorded_at_utc,
        )
        return RecordedDecision(feature=feature, decision=decision, created=created)
