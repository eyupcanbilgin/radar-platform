"""Telegram kurulumunu doğrular: tek bir test mesajı gönderir.

Token/chat id YALNIZ ortamdan okunur (.env). Hata durumunda ne yapılacağını söyler.
Kullanım: .venv/Scripts/python scripts/telegram_check.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from enricher.telegram import (  # noqa: E402
    NotConfigured,
    TelegramSender,
    load_env_file,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env_file(REPO / ".env")
    sender = TelegramSender()
    if not sender.configured:
        sys.exit(
            "HATA: TELEGRAM_BOT_TOKEN ve/veya TELEGRAM_CHAT_ID tanımlı değil.\n"
            "Çözüm: .env.example dosyasını .env olarak kopyala ve doldur "
            "(adımlar: docs/TELEGRAM-KURULUM.md)"
        )
    try:
        sender(
            "[TEST] radar-signal kurulum doğrulaması.\n"
            "Bu mesajı görüyorsan bildirim hattı çalışıyor.\n"
            "Not: Araştırma sistemidir; yatırım tavsiyesi değildir."
        )
    except NotConfigured as exc:
        sys.exit(f"HATA: {exc}")
    except Exception as exc:
        sys.exit(
            f"HATA: teslimat başarısız — {exc}\n"
            "Kontrol listesi: (1) token doğru mu, (2) chat id doğru mu, "
            "(3) bota Telegram'dan en az bir mesaj gönderdin mi?"
        )
    print("OK: test mesajı gönderildi. Telegram'ını kontrol et.")


if __name__ == "__main__":
    main()
