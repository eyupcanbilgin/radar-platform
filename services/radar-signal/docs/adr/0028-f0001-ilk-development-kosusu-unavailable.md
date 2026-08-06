# ADR-0028 — F-0001 İlk Development Koşusu: Unavailable

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** F-0001, Signal ADR-0024–0027

## Kanıt

Manifest hash'i
`60deaf799f19b167f0d378780fac76c1f3246db703952be096a3403bc346c53f` olan gerçek
Development verisiyle iki venue ve iki zorunlu leave-one-family-out seti koşuldu. Locked OOS
sınırı `2026-08-04T00:00:00Z` açılmadı. Koşu code SHA'sı `a8869dfa5dcf`, Registry kaydı
`E-20260806-075720-32e7c7`dir.

Binance futures 22.704 kesintisiz saat; Coinbase spot 22.694 saat ve toplam 10 saatlik iki
gap taşıdı. Gap'ler doldurulmadan segmentlendi. Her venue'de 547 etiketlenebilir event-row
oluştu fakat ön-kayıtlı tetik ve cooldown kuralları altında bağımsız tetik sayısı `0/30`
kaldı. Ana koşu ve iki ablation bu nedenle `unavailable` oldu; performans kapıları
hesaplanmadı.

## Karar

1. Sonuç ret veya kabul değildir; örneklem/tetik kapsamı blocker'ıdır.
2. Eksik olaylar nötr veya başarısız tahmin sayılmaz. Direction null kalır.
3. Sonucu gördükten sonra persentil, pencere, cooldown veya asgari örneklem gevşetilmez.
4. Tarihî Registry satırı silinmez/değiştirilmez. Aynı kanıt kimliği mükerrer yazılmaz.
5. Yeniden ölçüm yalnız yeni PIT kapsamı ve yeni dataset snapshot ile aynı ön-kayıt altında
   yapılabilir; alternatif tetik tanımı ayrı hipotez ve ayrı ön-kayıt gerektirir.

Registry temel verdict sözlüğünde `unavailable` bulunmadığı ve kapanmamış `pending` satır
yasak olduğu için koşunun etkin Registry verdict'i append-only olayla
`invalid (unavailable evidence; data/sample blocker)` yapılır. Bu, hipotezin performans
reddi değildir; metrik üretmeyen koşunun DSR/deneme evrenine girmemesini sağlar. Evidence
gövdesindeki durum `unavailable` olarak korunur.

## Sonuç

F-0001 henüz ürün uyarısına bağlanamaz. Sıradaki doğru adım eşik ayarlamak değil, canlı PIT
kapsamını büyütmek ve tetik oluşumunu yön üretmeden coverage olarak izlemektir.
