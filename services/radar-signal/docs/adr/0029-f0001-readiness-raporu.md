# ADR-0029 — F-0001 Readiness Raporu

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** F-0001, Signal ADR-0025, ADR-0028

## Bağlam

İlk gerçek Development koşusu 0/30 bağımsız tetik nedeniyle `unavailable` oldu. Development
penceresi `2026-08-04T00:00:00Z` sınırında kilitlidir; bu tarihten sonra canlı biriken veriyi
geriye dönük Development kanıtına eklemek veya sonuç görülerek eşikleri gevşetmek yasaktır.
Tam iki-venue ölçümünü sırf hazır olup olmadığını anlamak için tekrarlamak da gereksiz Registry
ve hesap yükü yaratır.

## Karar

1. `scripts/f0001_readiness.py`, mühürlü ana ve iki ablation context setini ADR-0025 ile aynı
   manifest/variant/hash/Locked OOS kapısından geçirir.
2. Her variant için kullanılabilir fragility context'i, tetik hesabına girebilen context ve
   ön-kayıtlı cooldown sonrası bağımsız tetik sayısını config eşikleriyle raporlar.
3. Null fragility nötr sayılmaz; açık blocker üretir. Direction daima null kalır.
4. Rapor ileri olay etiketi veya performans metriği hesaplamaz, Locked OOS'u açmaz ve
   Registry'ye deney yazmaz.
5. `measurement_ready=true` yalnız ana ve iki ablation setinin tamamı ön-kayıtlı tetik
   örneklemi kapısını geçtiğinde oluşur. Venue/etiket kapıları gerçek koşuda ayrıca zorunludur.

İlk gerçek readiness raporunda ana ve funding-only set 1.743 kullanılabilir context ile 10
bağımsız context tetik, OI-only set 328 kullanılabilir context ile 0 tetik üretti. Bu sayı
venue etiketiyle kesişmiş performans örneklemi değildir; ADR-0028'deki gerçek ölçümde iki
venue için kesişen tetik sayısı 0 kalmıştır. Readiness bu nedenle `false`tur ve Registry satır
sayısı 22'den 22'ye değişmemiştir.

## Sonuç

Operatör eşik değiştirmeden yeniden ölçümün tetik açısından anlamlı olup olmadığını görebilir.
Mevcut Development seti hazır değilse seçenekler yalnız tarihsel PIT kapsamını meşru bir
kaynaktan tamamlamak veya farklı mekanizmayı ayrı hipotez olarak ön-kayıt etmektir.
