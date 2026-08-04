# ADR-0015 — Webhook HMAC ve Kalıcı Replay Koruma Kapısı

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** CR-002 P0-4/P2-6, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 3

## Bağlam

Enricher'ın üç mutasyon endpoint'i kimliksizdi. Ağa erişebilen bir istemci sahte signal,
fill veya exit olayı yazabilir; daha önce görülmüş geçerli bir isteği tekrar oynatabilirdi.
Sinyal kimliğinin uygulama seviyesindeki idempotency'si taşıma kimliği değildir ve fill/exit
sıralamasını kötü niyetli replay'den korumaz.

## Karar

1. Üç `/webhook/*` mutasyon endpoint'i, ham body'yi timestamp ve nonce ile bağlayan
   HMAC-SHA256 imzası ister. Secret yalnız `RADAR_SIGNAL_WEBHOOK_SECRET` environment
   değerinden okunur ve borsa/private API anahtarı değildir.
2. İmza mesajı `timestamp + "." + nonce + "." + raw_body`; signature header'ı
   `sha256=<64 lowercase hex>` biçimindedir. Karşılaştırma timing-safe yapılır.
3. Unix timestamp saat toleransı ve nonce retention saniyeleri `config/lifecycle.yaml`
   içindedir; pozitif integer değillerse config fail-loud reddedilir.
4. İmza ve tazelik doğrulandıktan sonra nonce ayrı SQLite store'a `BEGIN IMMEDIATE` ve
   primary key ile atomik yazılır. Aynı retention penceresindeki tekrar 409 döner.
5. Eksik/yanlış/bayat istemci kimliği 401; sunucuda secret olmaması 503'tür. Yanıtlarda
   secret, imza veya gelen header içeriği yansıtılmaz. `/health` açık kalır.
6. Resmî Freqtrade yerleşik webhook yapılandırması dinamik HMAC header desteği belgelemiyor.
   Bu nedenle doğrudan bağlantı açılmaz; ayrı signer adaptörü gelene kadar ingress kapısı
   hazır fakat canlı üretici entegrasyonu tamamlanmamış sayılır. URL-secret ve imzasız
   fallback kabul edilmez.

## Sonuçlar

Enricher mutasyon yüzeyi kimliksiz veya replay edilmiş olayları deftere ulaşmadan reddeder.
Nonce store restart sonrası korumayı sürdürür. Operasyonel Freqtrade bağlantısı için ayrıca
yerel bir imzalayıcı adaptör gerekir; bu ADR böyle bir adaptör varmış gibi davranmaz ve yön,
emir ya da strateji davranışını değiştirmez.
