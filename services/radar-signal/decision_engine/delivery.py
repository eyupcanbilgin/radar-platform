"""Deterministic hourly DecisionCard delivery through the durable outbox."""

from datetime import UTC, datetime

from decision_engine.decision import DecisionCardV1
from decision_engine.features import FeatureSnapshotV1
from decision_engine.ledger import DecisionLedger
from enricher.formatting import LEGAL_NOTE, assert_language_safe
from enricher.outbox import Outbox

HOURLY_DECISION_KIND = "hourly_decision"


def _labels(values: list[str]) -> str:
    return "; ".join(values) if values else "yok"


def build_hourly_decision_message(*, decision: DecisionCardV1, feature: FeatureSnapshotV1) -> str:
    """Render only immutable artifacts so replay and reconciliation are bit-identical."""
    if decision.feature_snapshot_id != feature.snapshot_id:
        raise ValueError("decision yanlış feature snapshot ile formatlanamaz")
    context_id = decision.context_snapshot_id or "yok"
    health = "hazır" if feature.ready else "kullanılamaz"
    lines = [
        f"[SAATLİK KARAR] {decision.instrument.symbol} · {decision.instrument.timeframe} · "
        f"{decision.as_of_utc.isoformat().replace('+00:00', 'Z')}",
        f"Sonuç: {decision.outcome}",
        f"Kimlik: {decision.decision_id}",
        f"Gerekçeler: {_labels(decision.reasons)}",
        f"Engeller: {_labels(decision.blockers)}",
        f"Veri sağlığı: {health} · eksikler: {_labels(feature.missing_features)}",
        f"Uyarılar: {_labels(decision.warnings)}",
        f"Snapshotlar: feature={feature.snapshot_id} · context={context_id}",
        "Mod: PAPER · real_orders=false · gerçek emir gönderilmez",
        "WAIT, yön veya nötr getiri ölçüldüğü anlamına gelmez.",
        f"Not: {LEGAL_NOTE}",
    ]
    text = "\n".join(lines)
    assert_language_safe(text)
    return text


class HourlyDecisionDelivery:
    def __init__(self, *, ledger: DecisionLedger, outbox: Outbox):
        self.ledger = ledger
        self.outbox = outbox

    def enqueue_item(self, item: dict, *, now: datetime | None = None) -> bool:
        decision = DecisionCardV1.model_validate(item["decision_payload"])
        feature = FeatureSnapshotV1.model_validate(item["feature_payload"])
        body = build_hourly_decision_message(decision=decision, feature=feature)
        return self.outbox.enqueue(
            signal_id=decision.decision_id,
            kind=HOURLY_DECISION_KIND,
            body=body,
            now=now or datetime.now(UTC),
        )

    def enqueue_decision(self, decision_id: str, *, now: datetime | None = None) -> bool:
        item = self.ledger.get(decision_id)
        if item is None:
            raise ValueError(f"teslim edilecek karar ledger'da yok: {decision_id}")
        return self.enqueue_item(item, now=now)

    def reconcile(self, *, limit: int, now: datetime | None = None) -> dict[str, int]:
        """Repair recent ledger→outbox gaps without an unbounded database scan."""
        stats = {"scanned": 0, "enqueued": 0, "existing": 0}
        for item in self.ledger.recent(limit=limit):
            stats["scanned"] += 1
            if self.enqueue_item(item, now=now):
                stats["enqueued"] += 1
            else:
                stats["existing"] += 1
        return stats
