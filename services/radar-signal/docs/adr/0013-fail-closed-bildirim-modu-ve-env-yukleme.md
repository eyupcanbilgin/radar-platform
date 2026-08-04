# ADR-0013 — Fail-Closed Bildirim Modu ve `.env` Yükleme

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** CR-002 P0-4/P2, `SINYAL-SPEC.md`, `docs/TELEGRAM-KURULUM.md`

## Bağlam

Outbox pompası Telegram credential'ları process environment içinde varsa Telegram'a,
yoksa sessizce console'a teslim ediyordu. Pompa servis `.env` dosyasını da yüklemiyordu;
yalnız doğrulama script'i kendine ait basit bir okuyucu kullanıyordu. Üretimde yanlış veya
eksik secret bu nedenle gerçek teslimat yapılmış gibi SENT durumuna geçen console mesajları
üretebilirdi.

## Karar

1. `RADAR_SIGNAL_DELIVERY_MODE` zorunlu ve yalnız `telegram|console` değerlerini kabul eder.
2. `telegram` modunda `TELEGRAM_BOT_TOKEN` ile `TELEGRAM_CHAT_ID` birlikte bulunmadan sender
   kurulmaz. Pompa ledger/outbox nesnelerini açmadan önce hata verir; kuyruk satırları PENDING
   kalır.
3. Credential eksikliği hiçbir koşulda otomatik console fallback'i oluşturmaz. `console`
   yalnız açık geliştirme seçimiyle etkinleşir.
4. Pompa ve Telegram doğrulama aracı ortak `load_env_file` okuyucusunu kullanır. Servis
   `.env` dosyası process environment değerlerini ezmez; malformed satırlar fail-loud olur.
5. Token/chat id config, log veya hata metnine yazılmaz. Env parse hataları satır numarası
   verir ancak satır içeriğini yansıtmaz.
6. Bu değişiklik yalnız bildirim taşımasını yapılandırır; gerçek emir/private API yüzeyi
   eklemez ve karar/yön semantiğini değiştirmez.

## Sonuçlar

Üretim yanlışlıkla console'a teslim edilmiş mesajları başarılı sayamaz. Yerel geliştirme
console modunu kullanmaya devam edebilir, fakat bu niyet `.env` veya process environment
içinde açıkça belirtilir. Telegram kesintileri mevcut outbox retry/backoff davranışıyla
PENDING kalmaya devam eder.
