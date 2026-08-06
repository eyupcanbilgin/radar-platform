# ADR-0027 — F-0001 Gerçek Context Sözleşmesi Düzeltmesi

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0022, ADR-0024, ADR-0025; `decision-context/v1`

## Bağlam

İlk gerçek F-0001 kanıt koşusu, metrik veya Registry kaydı üretmeden önce fail-closed durdu.
Event-row adaptörü sentetik testlerde `data_cutoff_at_utc` ve yön kapısını üst seviye geçici
alanlardan okurken sürümlü platform sözleşmesi bu alanları sırasıyla `snapshot` ve
`data_quality` altında taşır. Mühürlü gerçek context setleri doğru sözleşmeyi kullanıyordu.

## Karar

1. Event-row üreticisi cutoff değerini `snapshot.data_cutoff_at_utc`, yön kapısını
   `data_quality.directional_decision_allowed` alanından okur.
2. Sentetik test payload'ları gerçek `decision-context/v1` alan yerleşimini kullanır ve
   look-ahead/direction-null regresyonlarını aynı alanlarda sınar.
3. Ön-kayıt eşikleri, veri, Locked OOS sınırı, yön politikası ve ölçüm yöntemi değişmez.
   Başarısız ilk girişim performans sonucu veya Registry denemesi değildir.

## Sonuç

F-0001 runner mühürlü MCP context setlerini sürümlü platform sözleşmesine göre tüketebilir;
entegrasyon uyumsuzluğu artık sentetik regresyon testinde yakalanır.
