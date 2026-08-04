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

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from enricher.fill import mark_reference_open
from enricher.ledger import SignalLedger
from enricher.lifecycle import EXIT_STATES, IllegalTransition, State
from enricher.outbox import Outbox
from enricher.pipeline import SignalEvent, SignalPipeline
from enricher.policy import load_lifecycle
from enricher.webhook_auth import (
    NONCE_PATTERN,
    NonceStore,
    parse_request_time,
    require_fresh,
    verify_signature,
)

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
DB_DIR = Path(os.environ.get("RADAR_SIGNAL_DB_DIR", REPO / "var"))

app = FastAPI(title="radar-signal enricher", version="0.1.0")


async def _authenticate_webhook(request: Request) -> None:
    secret = os.environ.get("RADAR_SIGNAL_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="webhook authentication yapılandırılmamış")
    timestamp = request.headers.get("X-Radar-Timestamp", "")
    nonce = request.headers.get("X-Radar-Nonce", "")
    signature = request.headers.get("X-Radar-Signature", "")
    if not NONCE_PATTERN.fullmatch(nonce):
        raise HTTPException(status_code=401, detail="webhook authentication başarısız")
    try:
        auth_config = load_lifecycle()["webhook_auth"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="webhook authentication yapılandırılmamış"
        ) from exc
    try:
        request_time = parse_request_time(timestamp)
        now = datetime.now(UTC)
        require_fresh(
            request_time=request_time,
            now=now,
            max_clock_skew_seconds=int(auth_config["max_clock_skew_seconds"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="webhook authentication başarısız") from exc
    body = await request.body()
    if not verify_signature(
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
        supplied=signature,
    ):
        raise HTTPException(status_code=401, detail="webhook authentication başarısız")
    with NonceStore(DB_DIR / "webhook-nonces.sqlite") as nonces:
        accepted = nonces.reserve(
            nonce=nonce,
            request_time=request_time,
            accepted_at=now,
            retention_seconds=int(auth_config["nonce_retention_seconds"]),
        )
    if not accepted:
        raise HTTPException(status_code=409, detail="webhook replay reddedildi")


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


class FillIn(BaseModel):
    signal_id: str
    fill_price: float | None = None


@app.post("/webhook/fill", dependencies=[Depends(_authenticate_webhook)])
def webhook_fill(payload: FillIn) -> dict:
    """Referans pozisyon açıldı: SIGNAL_SENT → REFERENCE_OPEN."""
    pipe = _pipeline()
    try:
        state = mark_reference_open(
            pipe.ledger, signal_id=payload.signal_id, fill_price=payload.fill_price
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IllegalTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        pipe.ledger.close()
        pipe.outbox.close()
    return {"signal_id": payload.signal_id, "state": state.value}


@app.post("/webhook/signal", dependencies=[Depends(_authenticate_webhook)])
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


@app.post("/webhook/exit", dependencies=[Depends(_authenticate_webhook)])
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
    except IllegalTransition as exc:
        # Yaşam döngüsü ihlali istemci hatasıdır, sunucu arızası değil: 409 ile
        # geri bildirilir ki çağıran (freqtrade/operatör) sırayı düzeltebilsin.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
