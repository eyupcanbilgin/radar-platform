# ADR-0035 — Hafif Production Context-Set Loader

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0025, ADR-0031, ADR-0032, ADR-0034

## Bağlam

Saatlik runtime, F-0001 combined baseline manifestini doğrulamak için
`scripts/run_f0001_evidence.py` içindeki özel fonksiyonları import ediyordu. Evidence modülü
Feather venue verisi için pandas yüklediğinden, canlı daemon yalnız JSON/hash doğrulaması
yapmasına rağmen tam araştırma dataframe bağımlılığını istiyordu. Bu sınır macOS'ta ayrı,
dar runtime ortamı kurulmasını gereksiz yere engelliyordu.

## Karar

1. Context-set şema, variant, excluded-feature, Development/Locked OOS sınırı, dosya sayısı
   ve SHA-256 doğrulaması `decision_engine/context_sets.py` production modülüne taşınır.
2. Saatlik runtime ve exact-hour forward observer bu modülü doğrudan kullanır. Modül pandas,
   Feather, venue outcome, Registry veya research runner import edemez.
3. Evidence ve readiness CLI'ları ayrı doğrulama kopyası tutmaz; aynı loader'ı kullanır.
   Evidence'ın geçmiş özel isimleri yalnız mevcut test/çağrı uyumluluğu için alias kalır.
4. Doğrulama semantiği değişmez: config sınırı veya tek dosya hash'i uyuşmazsa fail-closed;
   Locked OOS açılmaz, eksik veri nötrleştirilmez ve direction üretilmez.

## Sonuç

Canlı paper runtime, araştırma dataframe paketini yüklemeden mühürlü baseline'ı doğrulayabilir.
Bu refactor yeni ölçüm, forward backfill, outcome, Registry, alert veya yön davranışı açmaz.
