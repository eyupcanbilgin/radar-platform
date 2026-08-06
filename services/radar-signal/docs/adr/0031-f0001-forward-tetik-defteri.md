# ADR-0031 — F-0001 Forward Tetik Defteri

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030 ön-kaydı, F-0001

## Karar

1. `ForwardTriggerLedger`, her UTC saat için tek `f0001-forward-trigger/v1` payload'ını
   SQLite'a append-only yazar. SQL trigger'ları UPDATE, DELETE ve çakışan INSERT'i engeller.
2. Observation kimliği ve hash'i context snapshot/content hash'i, mühürlü baseline hash'i,
   trigger config hash'i ve sonuçsuz tetik gövdesinden deterministik türetilir. Aynı içerikli
   retry idempotent, farklı içerikli aynı saat hatadır.
3. `scripts/observe_f0001_trigger.py`, baseline context set manifestini ADR-0030 config
   hash'i ve ADR-0025 sözleşmesiyle doğrular; exact-hour `decision-context/v1` girdisini katı
   Pydantic modeliyle okur.
4. İlk kayıt ön-kayıt başlangıcından eski olamaz. Sonraki kayıtlar yalnız ileri sırada
   eklenir; atlanan saatler `missing_forward_hours:<n>` blocker'ı olur ve doldurulmaz.
5. Fragility null veya tarihçe yetersizse `status=unavailable`, `triggered=null` yazılır.
   Eksiklik `false` tetik veya nötr skor değildir.
6. Payload sabit olarak `direction=null`, `outcome_read=false`, `registry_write=false` ve
   `alert_emitted=false` taşır. Bu defter karar, uyarı veya performans kanıtı değildir.

## İşletim

İlk gerçek kayıt `2026-08-07T00:00:00Z` veya sonrasındaki exact-hour context ile yapılabilir.
Kod bu tarihten önce gerçek smoke/backfill çalıştırılmadan sentetik testlerle doğrulanmıştır.
Mühürlü baseline ham context seti Git'e girmez; MCP'nin deterministik research-contexts
üreticisiyle yeniden oluşturulur ve config'deki hash ile eşleşmek zorundadır.
