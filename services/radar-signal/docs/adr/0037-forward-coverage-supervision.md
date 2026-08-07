# ADR-0037 — Forward Coverage Supervision

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030, ADR-0033, ADR-0034, ADR-0036

## Bağlam

F-0001 forward gözlemi saatlik runtime'a bağlı ve coverage CLI'ı salt-okunur rapor
üretebiliyordu. Ancak macOS supervision yalnız producer, karar runtime'ı ve outbox pump'ı
çalıştırıyordu; coverage durumu kalıcı bir dosyaya düzenli yazılmıyordu. One-shot coverage
CLI'ını `KeepAlive` ile denetlemek de sürekli restart döngüsü yaratırdı.

## Karar

1. Coverage CLI'ı isteğe bağlı `--output` ile raporu atomik JSON yazar; aynı payload stdout'a
   da basılır. Forward ledger salt-okunur açılmaya devam eder.
2. macOS renderer dördüncü `com.radar.signal-coverage` ajanını üretir. Ajan `KeepAlive`
   kullanmaz; supervision config v2'deki pozitif `StartInterval` ile tek-sefer raporlar.
3. Ajan aynı forward ledger'ı okur ve son durumu state root altında
   `signal/f0001-forward-coverage.json` dosyasına yazar. Eksik saat ve unavailable gözlem
   blocker olarak kalır; sıfır/nötr olaya çevrilmez.
4. Rapor outcome okumaz, Registry'ye yazmaz, bildirim üretmez, geçmiş gözlem eklemez ve
   `direction=null` taşır. Dosyanın güncel olması tek başına sağlıklı coverage kanıtı değildir;
   raporun status/blocker alanları ayrıca denetlenir.

## Sonuç

MacBook operatörü append-only forward defterinin güncel coverage görünümünü ayrı komut
çalıştırmadan izleyebilir. Supervision çalışma zamanı kanıt üretmeye veya eksik saati
backfill etmeye başlamaz.
