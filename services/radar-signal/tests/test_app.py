"""Webhook adaptörü testleri (FastAPI ince katman)."""

import pytest
from fastapi.testclient import TestClient

from enricher import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DB_DIR", tmp_path)
    return TestClient(app_module.app)


PAYLOAD = {
    "asset": "BTC",
    "strategy": "S0001",
    "direction": "LONG",
    "candle_close_utc": "2026-08-03T12:00:00+00:00",
    "enter_tag": "ema_cross_up",
    "rationale": "EMA20 EMA50'yi yukarı kesti",
    "counter_evidence": "Hacim ortalamanın altında",
    "entry_reference": 61250.0,
    "invalidation": 60100.0,
    "inputs_available": {
        "candle_close": True,
        "price": True,
        "atr": True,
        "regime": True,
        "blackout_calendar": True,
    },
}


def test_signal_webhook_creates_and_queues(client):
    r = client.post("/webhook/signal", json=PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["signal_id"] == "BTC-S0001-20260803-1200-L-01"
    assert body["state"] == "APPROVED" and body["queued"] is True


def test_repeated_webhook_is_idempotent(client):
    first = client.post("/webhook/signal", json=PAYLOAD).json()
    second = client.post("/webhook/signal", json=PAYLOAD).json()
    assert first["signal_id"] == second["signal_id"]
    assert second["queued"] is False


def test_missing_required_input_blocks(client):
    payload = {**PAYLOAD, "inputs_available": {**PAYLOAD["inputs_available"], "price": False}}
    body = client.post("/webhook/signal", json=payload).json()
    assert body["state"] == "BLOCKED" and "ZORUNLU GİRDİ EKSİK" in body["block_reason"]


def test_invalid_direction_rejected_by_schema(client):
    r = client.post("/webhook/signal", json={**PAYLOAD, "direction": "up"})
    assert r.status_code == 422


def test_invalid_exit_state_rejected(client):
    client.post("/webhook/signal", json=PAYLOAD)
    r = client.post(
        "/webhook/exit",
        json={
            "signal_id": "BTC-S0001-20260803-1200-L-01",
            "exit_state": "KAFAMA_GORE",
            "reason_code": "x",
        },
    )
    assert r.status_code == 422
    assert "geçersiz çıkış durumu" in r.json()["detail"]


def test_exit_before_fill_is_409_not_500(client):
    """Yaşam döngüsü ihlali istemci hatasıdır; canlı duman testinde 500 dönüyordu."""
    client.post("/webhook/signal", json=PAYLOAD)
    r = client.post(
        "/webhook/exit",
        json={
            "signal_id": "BTC-S0001-20260803-1200-L-01",
            "exit_state": "STOP_EXIT",
            "reason_code": "atr_stop_touched",
        },
    )
    assert r.status_code == 409
    assert "geçişi tanımsız" in r.json()["detail"]


def test_fill_then_exit_succeeds(client):
    client.post("/webhook/signal", json=PAYLOAD)
    sid = "BTC-S0001-20260803-1200-L-01"
    # APPROVED → SIGNAL_SENT (teslimat), sonra fill
    from enricher.ledger import SignalLedger
    from enricher.lifecycle import State as S

    with SignalLedger(app_module.DB_DIR / "signals.sqlite") as led:
        led.apply(signal_id=sid, target=S.SIGNAL_SENT, reason_code="outbox_delivered")

    assert (
        client.post("/webhook/fill", json={"signal_id": sid, "fill_price": 61300.0}).json()["state"]
        == "REFERENCE_OPEN"
    )
    r = client.post(
        "/webhook/exit",
        json={
            "signal_id": sid,
            "exit_state": "STOP_EXIT",
            "reason_code": "atr_stop_touched",
            "reference_price": 60100.0,
        },
    )
    assert r.status_code == 200 and r.json()["state"] == "STOP_EXIT"


def test_exit_for_unknown_signal_is_404(client):
    r = client.post(
        "/webhook/exit",
        json={"signal_id": "YOK-1", "exit_state": "STOP_EXIT", "reason_code": "x"},
    )
    assert r.status_code == 404


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["lifecycle_version"] == "1.0"
