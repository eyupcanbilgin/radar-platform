# ADR-0033 — F-0001 Forward Coverage Status

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030, ADR-0031, ADR-0032

## Karar

1. `scripts/f0001_forward_coverage.py`, F-0001 append-only tetik defterini salt-okunur
   özetler. Beklenen UTC saatlerini ön-kayıt başlangıcından son due saate kadar sayar.
2. Yazılmış gözlem coverage'ı ile veri kullanılabilirliği ayrıdır. Eksik defter satırları
   `missing_forward_hours:<n>`, yazılmış fakat unavailable satırlar
   `unavailable_forward_observations:<n>` blocker'ı olur. İkisi de tetiksiz/sakin saat
   sayılmaz.
3. Coverage oranı yalnız `recorded / expected` oranıdır; kabul eşiği veya performans metriği
   değildir. Tetikli ve tetiksiz sayıları yalnız defterde açık boolean bulunan satırlardan
   gelir; null değer `false` yapılmaz.
4. Varsayılan rapor kesimi, config'deki grace süresine göre son due UTC saatidir. Açık
   `--as-of` yalnız geçmiş salt-okunur görünüm üretir; backfill veya defter yazımı yapmaz.
5. Rapor sabit olarak `direction=null`, `outcome_read=false`, `registry_write=false` ve
   `alert_emitted=false` taşır. Forward değerlendirmeyi veya ürün uyarısını açmaz.

## Sonuç

Operatör gerçek saatlik işletimin coverage ve unavailable boşluklarını sonuçlara bakmadan
izleyebilir. Gerçek daemon'ın baseline ile çalıştırılması ve ilk forward satırların oluşması
ayrı operasyon adımı olarak açık kalır.
