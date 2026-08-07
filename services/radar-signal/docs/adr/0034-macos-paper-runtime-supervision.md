# ADR-0034 — macOS Paper Runtime Supervision

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0032, ADR-0033; MCP ADR-0006

## Karar

1. `render_macos_launch_agents.py`, producer daemon, saatlik Signal daemon ve outbox pump
   için üç `launchd` plist'i üretir. Araç bunları kurmaz, yüklemez veya haricî mesaj göndermez.
2. Kod checkout'u ile çalışma zamanı state'i ayrılır. Checkout tüm untracked dosyalar dahil
   temiz olmalıdır; PIT, heartbeat, ledger, outbox, context ve loglar açık `--state-root`
   altında kalır.
3. F-0001 combined `context-set.json` state root'ta bulunmalı ve checkout'taki ön-kayıt
   config hash'iyle eşleşmelidir. Eksik/farklı baseline ile agent üretilmez.
4. Producer ve Signal aynı saat sınırında yarışamaz. Producer publish grace ve Signal
   decision grace değerleri `config/macos_supervision.yaml` içindedir; Signal grace kesin
   olarak producer grace'ten büyük olmak zorundadır. Catch-up sıfırdır; forward backfill yoktur.
5. Plist'ler secret/API key taşımaz. Teslimat modu açıkça `console|telegram` seçilir;
   varsayılan console'dur. Telegram credential'ı plist'e gömülemez.
6. Ajanlar `KeepAlive` ve `RunAtLoad` kullanır; stdout/stderr ayrı state loglarına gider.
   Üretilen plist atomik yazılır ve yalnız kullanıcı tarafından okunabilir (`0600`).

## Sonuç

MacBook yeniden başlatmalarında süreçlerin tekrar ayağa kalkması için denetlenebilir launchd
konfigürasyonu üretilebilir. Gerçek kurulum opt-in operasyon adımıdır; üretilen plist'in varlığı
uptime veya coverage kanıtı sayılmaz. Sağlık hâlâ MCP heartbeat/status ve F-0001 coverage
raporuyla ölçülür.
