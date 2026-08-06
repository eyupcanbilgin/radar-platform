# ADR-0030 — F-0001 Forward Tetik Gözlemi Ön-Kaydı

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi — kod öncesi ön-kayıt
- **İlgili:** F-0001, Signal ADR-0028, ADR-0029

## Bağlam

Development koşusu venue etiketleriyle kesişen 0/30 tetik nedeniyle `unavailable` oldu.
Development penceresi kilitlidir; 4 Ağustos sonrasında biriken veriyi geriye eklemek veya
sonuca bakarak eşikleri değiştirmek yasaktır. Yine de canlı PIT zincirinin gelecekte yeterli
OI geçmişi ve tetik fırsatı üretip üretmediği, outcome açmadan prospektif gözlenebilir.

## Ölçümden önce dondurulan karar

1. Gözlem `2026-08-07T00:00:00Z` anında başlar. Daha eski saatler forward deftere backfill
   edilmez.
2. Başlangıç dağılımı yalnız ADR-0028'de kullanılan mühürlü `combined` Development context
   setidir; manifest SHA-256 değeri config'de sabittir.
3. Canlı girdiler exact-hour `decision-context/v1` olur. `data_cutoff_at_utc <= as_of_utc`,
   `direction=null` ve kapalı yön kapısı zorunludur. Null fragility tetiksiz/sakin sayılmaz;
   `unavailable` gözlemdir.
4. Tetik hesabı F-0001'in mevcut config kurallarını aynen kullanır: 90 gün, en az 45 gün/720
   kullanılabilir saat, 80. persentil ve 24 saat cooldown. Bu ön-kayıt eşik değiştirmez.
5. Defter append-only ve idempotenttir. Aynı saat aynı içerikle retry olabilir; farklı
   içerikle overwrite/update/delete yasaktır. Saat boşluğu açık blocker olarak görünür.
6. Defter yalnız trigger coverage taşır. İleri OHLCV/outcome, precision/recall, performans,
   uyarı kartı veya yön üretmez; Experiment Registry'ye yazmaz ve outbox'a mesaj göndermez.

## Açılma kapısı

Bu gözlem F-0001'i kabul etmez. Yeni değerlendirme ancak OI geçmiş kapısı ve ön-kayıtlı
bağımsız tetik örneklemi sağlandıktan sonra, outcome görülmeden ayrı bir değerlendirme kartı
ile açılabilir. Forward defterdeki sonuçsuz tetik sayısı tek başına ürün uyarısı değildir.
