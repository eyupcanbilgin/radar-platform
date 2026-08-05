# ADR-0020 — Dönem ve Venue Kırılganlık Kapısı

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0014, ADR-0019, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 2

## Bağlam

ADR-0019 çoklu-deneme, seçim, parametre ve veri ailesi kırılganlığını görünür yaptı; ancak
bir adayın yalnız belirli bir tarih diliminde veya tek borsanın mikro yapısında çalışmasını
ayrı bir kapıyla ölçmüyordu. Tek toplu getiri, zayıf dönemleri ve venue bağımlılığını
ortalama içinde saklayabilir. Binance dışı gerçek venue veri seti henüz repoda yoktur.

## Karar

1. `statistical_gates/version` 1.1 ve çıktı sözleşmesi `phase2-statistical-gates/v2` olur.
2. Her yeni aday, ön-kayıtlı en az üç Development dönemi ile en az iki bağımsız venue için
   grup bazlı net-getiri serileri sağlar. Grup adları ve sınırları sonuç görülmeden belirlenir.
3. Her grup `realistic` ve `taker_heavy` senaryolarını ve config'deki asgari gözlem sayısını
   taşır. Eksik, kısa veya sonlu olmayan seri fail-loud durur; nötr/sıfırla doldurulmaz.
4. Her boyut ve maliyet senaryosu için grup ortalamalarının ortak ortalaması referanstır.
   En kötü grubun bu referansa göre korunma oranı ile pozitif grup oranı config'deki göreli
   eşikleri birlikte geçmelidir. Ortak ortalama pozitif değilse kapı başarısızdır.
5. Dönem ve venue boyutlarının ikisi de iki maliyet senaryosunda geçmeden genel kapı geçmez.
6. Bu değişiklik yalnız değerlendirme altyapısıdır. Gerçek venue verisi üretmez, Locked OOS
   açmaz, Registry'ye yazmaz ve S-0003/S-0004 kararlarını geriye dönük değiştirmez.

## Sonuçlar

Sonraki ön-kayıtlı hipotez, tek dönem veya tek venue başarısını genellenebilir avantaj gibi
sunamayacaktır. İkinci bağımsız venue verisi hazır olana kadar gerçek değerlendirme
fail-closed kalır; sentetik test başarısı araştırma kanıtı sayılmaz.
