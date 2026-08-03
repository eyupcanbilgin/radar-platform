"""Telegram teslimatçısı — outbox'ın kullandığı gönderici.

Token ve chat id YALNIZ ortam değişkeninden okunur (`.env` → TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID). Config dosyasına veya koda yazılmaz, log'a basılmaz; hata
mesajlarında token asla yer almaz.

Gönderici bilinçli olarak "aptal"dır: yeniden deneme, kuyruk ve idempotency
outbox'ın işidir (enricher/outbox.py).
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT = 15.0


class NotConfigured(Exception):
    """TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanımlı değil."""


class TelegramSender:
    def __init__(self, *, token: str | None = None, chat_id: str | None = None):
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

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
