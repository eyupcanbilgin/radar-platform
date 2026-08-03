"""FastAPI webhook adaptörü — ince katman; iş mantığı `pipeline.py`'dedir.

freqtrade webhook'u buraya POST eder; enricher sinyali kapılardan geçirip deftere
ve outbox'a yazar. Teslimat `scripts/pump.py` tarafından yürütülür (ayrı süreç:
webhook isteği teslimat gecikmesini beklemez).

Çalıştırma:
    .venv/Scripts/python -m uvicorn enricher.app:app --host 127.0.0.1 --port 8129
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from enricher.ledger import SignalLedger
from enricher.lifecycle import EXIT_STATES, State
from enricher.outbox import Outbox
from enricher.pipeline import SignalEvent, SignalPipeline
from enricher.policy import load_lifecycle

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
DB_DIR = Path(os.environ.get("RADAR_SIGNAL_DB_DIR", REPO / "var"))

app = FastAPI(title="radar-signal enricher", version="0.1.0")


def _pipeline() -> SignalPipeline:
    lifecycle = load_lifecycle()
    ob_cfg = lifecycle["outbox"]
    return SignalPipeline(
        ledger=SignalLedger(DB_DIR / "signals.sqlite"),
        outbox=Outbox(
            DB_DIR / "outbox.sqlite",
            max_attempts=int(ob_cfg["max_attempts"]),
            backoff_seconds=list(ob_cfg["retry_backoff_seconds"]),
            late_delivery_after_minutes=int(ob_cfg["late_delivery_after_minutes"]),
        ),
        lifecycle=lifecycle,
    )


class SignalIn(BaseModel):
    asset: str
    strategy: str
    direction: str = Field(pattern="^(LONG|SHORT)$")
    candle_close_utc: datetime
    enter_tag: str
    rationale: str = ""
    counter_evidence: str = ""
    entry_reference: float | None = None
    invalidation: float | None = None
    timeframe: str = "15m"
    snapshot_id: str | None = None
    regime_line: str = "REJİM ÇEVRİMDIŞI — değerlendirilemedi"
    data_health: str = "bilinmiyor"
    inputs_available: dict[str, bool] = Field(default_factory=dict)
    blackout_reason: str | None = None


class ExitIn(BaseModel):
    signal_id: str
    exit_state: str
    reason_code: str
    reference_price: float | None = None


@app.post("/webhook/signal")
def webhook_signal(payload: SignalIn) -> dict:
    pipe = _pipeline()
    try:
        res = pipe.handle(SignalEvent(**payload.model_dump()), now=datetime.now(UTC))
    finally:
        pipe.ledger.close()
        pipe.outbox.close()
    return {
        "signal_id": res.signal_id,
        "state": res.state.value,
        "queued": res.queued,
        "block_reason": res.block_reason,
        "degraded_flags": res.degraded_flags or [],
    }


@app.post("/webhook/exit")
def webhook_exit(payload: ExitIn) -> dict:
    if payload.exit_state not in {s.value for s in EXIT_STATES}:
        raise HTTPException(
            status_code=422,
            detail=f"geçersiz çıkış durumu: {payload.exit_state}; "
            f"izinli: {sorted(s.value for s in EXIT_STATES)}",
        )
    pipe = _pipeline()
    try:
        res = pipe.handle_exit(
            signal_id=payload.signal_id,
            exit_state=State(payload.exit_state),
            reason_code=payload.reason_code,
            reference_price=payload.reference_price,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        pipe.ledger.close()
        pipe.outbox.close()
    return {"signal_id": res.signal_id, "state": res.state.value, "queued": res.queued}


@app.get("/health")
def health() -> dict:
    pipe = _pipeline()
    try:
        return {
            "status": "ok",
            "lifecycle_version": pipe.lifecycle["version"],
            "outbox": pipe.outbox.counts(),
            "open_references": len(pipe.ledger.in_state(State.REFERENCE_OPEN)),
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
        }
    finally:
        pipe.ledger.close()
        pipe.outbox.close()
