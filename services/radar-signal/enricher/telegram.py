"""Telegram teslimatçısı — outbox'ın kullandığı gönderici.

Token ve chat id YALNIZ ortam değişkeninden okunur (`.env` → TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID). Config dosyasına veya koda yazılmaz, log'a basılmaz; hata
mesajlarında token asla yer almaz.

Gönderici bilinçli olarak "aptal"dır: yeniden deneme, kuyruk ve idempotency
outbox'ın işidir (enricher/outbox.py).
"""

import logging
import os
import re
from collections.abc import MutableMapping
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT = 15.0


class NotConfigured(Exception):
    """TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanımlı değil."""


class DeliveryConfigurationError(ValueError):
    """Bildirim modu eksik veya güvenli olmayan biçimde yapılandırılmış."""


def load_env_file(path: Path, *, environ: MutableMapping[str, str] | None = None) -> None:
    """Load a local env file without overriding process-level configuration."""
    target = environ if environ is not None else os.environ
    if not path.exists():
        return
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise DeliveryConfigurationError(f".env satırı geçersiz: line={number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise DeliveryConfigurationError(f".env anahtarı geçersiz: line={number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target.setdefault(key, value)


class TelegramSender:
    def __init__(self, *, token: str | None = None, chat_id: str | None = None):
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN", "") if token is None else token
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") if chat_id is None else chat_id

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def __call__(self, body: str) -> None:
        if not self.configured:
            raise NotConfigured(
                "TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID tanımlı değil; .env dosyasına ekleyin "
                "(değerler koda/config'e yazılmaz)"
            )
        resp = httpx.post(
            f"{API_BASE}/bot{self._token}/sendMessage",
            json={"chat_id": self._chat_id, "text": body, "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            # Token'ı sızdırmamak için yalnız durum kodu ve gövde özeti loglanır.
            raise RuntimeError(f"Telegram teslimatı başarısız: HTTP {resp.status_code}")


class ConsoleSender:
    """Telegram yokken kullanılan teslimatçı (geliştirme ve dry-run kurulumu)."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, body: str) -> None:
        self.sent.append(body)
        logger.info("BİLDİRİM (konsol):\n%s", body)


def sender_from_environment(
    *, environ: MutableMapping[str, str] | None = None
) -> TelegramSender | ConsoleSender:
    """Select delivery explicitly; missing credentials never degrade to console."""
    source = environ if environ is not None else os.environ
    mode = source.get("RADAR_SIGNAL_DELIVERY_MODE", "").strip().lower()
    if mode == "console":
        return ConsoleSender()
    if mode != "telegram":
        raise DeliveryConfigurationError(
            "RADAR_SIGNAL_DELIVERY_MODE açıkça telegram veya console olmalı"
        )
    sender = TelegramSender(
        token=source.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=source.get("TELEGRAM_CHAT_ID", ""),
    )
    if not sender.configured:
        raise NotConfigured(
            "delivery mode telegram ancak TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID eksik"
        )
    return sender
