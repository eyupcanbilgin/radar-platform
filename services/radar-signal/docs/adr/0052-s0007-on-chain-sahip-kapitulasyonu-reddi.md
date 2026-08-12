# ADR-0052 — S-0007 reddedildi: zincir üstü sahip kapitülasyonu yön üretmiyor

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0006, Platform ADR-0004 §4, Signal ADR-0050 (veri yüzeyi),
  ADR-0043 (S-0005 reddi), ADR-0045 (S-0006 reddi), ADR-0003 (Registry)

## Bağlam

S-0007, `docs/hypotheses/S-0007.md` içinde **ölçümden önce** (commit `37553b5`) dondurulmuş
beşinci yönsel ailedir: kısa vadeli sahiplerin zincir üstünde sürdürülmüş **zararla** coin
harcaması sonraki 24 saat için pozitif, sürdürülmüş **kârla** harcaması negatif yön
beklentisi taşır. Mekanizma arz tükenmesidir.

Ölçüm, kartın uygulandığı commit'te (`17295a4e40da`) **temiz ağaçla** koşuldu.

## Sonuç: REDDEDİLDİ

Registry: `E-20260811-133935-762246`, `dataset_snapshot 568c86f5…` (MANIFEST-20260811),
`git_dirty: False`.

| Ölçüt | Değer | Kapı |
|---|---|---|
| İşlem sayısı | 387 | ≥ 100 ✔ |
| Net getiri `realistic` | **−%36.65** | > 0 ✘ |
| Net getiri `taker_heavy` | **−%53.52** | > 0 ✘ |
| `buy_and_hold` | −%13.56 / −%15.47 | aşılmalı ✘ |
| `simple_trend` | +%6.69 / −%12.80 | aşılmalı ✘ |
| Permütasyon `p` | **0.4213** | < 0.05 ✘ |
| Fold tutarlılığı | **%42.9** | ≥ %60 ✘ |

Sekiz ret ölçütü tetiklendi. **Yönsel skor: 5 aile, 5 ret.**

Örneklem ön-kontrolü doğru çıktı: karta veriye bakmadan "~378 işlem" yazılmıştı, ölçüm 387
üretti. Ret bir örneklem yetersizliği değildir.

## Kararlar

### 1. Ters çevirme yapılmadı

Sonuç hipotezin **tersi** yönde çıktı. Sinyali ters çevirmek `realistic` tarafta büyük bir
artıya dönerdi. Çevrilmedi. İki sebep, sırasıyla:

1. **Kural.** Ters çevirme, sonucu gördükten sonra yönü değiştirmektir; ön-kaydın tanımı
   gereği yasaktır. S-0006'da aynı durum yaşandı ve orada da çevrilmedi (ADR-0045).
2. **İstatistik.** Çevirmek isteseydik bile çevrilecek kanıt yok: `p = 0.4213`, gözlenen
   yönsel etki şanstan ayırt edilemiyor; fold tutarlılığı %42.9 ile yazı-turadan farksız.
   Negatif getiri "ters sinyal bulduk" demek değil, **"bu büyüklükte yönsel bilgi yok"**
   demektir.

Ters yönlü bir hipotez ancak yeni ve ayrı bir ön-kayıtla, kendi mekanizma gerekçesiyle ve
deneme sayacına **yeni bir deneme** olarak girerek sınanabilir.

### 2. Aile kapanır; eşik değiştirilerek yeniden koşulmaz

Kart §4.8 gereği S-0007 kapanmıştır. `sopr_smooth_days`, `sopr_dist_days` ve 80/20 bandı
sonucu görüp aranmayacaktır.

Karttaki beyan edilmiş sınırlama (günlük seride 30 gün = 30 örnek, çözünürlük ~3.3 puan)
ret sonrası bir mazerete dönüştürülmemektedir: pencere büyütülüp yeniden koşulmayacaktır.

### 3. DSR / PBO / ±%20 kapıları yine çalışmadı

Base reddedildiği için tutunma oranı tanımsızdır ve ek kapılar `not_evaluated` döner.
**Bu, üst üste üçüncü kez böyle olmuştur** (S-0005, S-0006, S-0007). Kapılar kuruludur ve
sentetik kabul testleriyle korunur; gerçek veride ilk kez base'i ayakta kalan bir ailede
çalışacaklardır. Bugün için dürüst ifade şudur: **bu kapıların gerçek bir aday üzerindeki
davranışı hâlâ gözlenmemiştir.**

### 4. Veri yüzeyi kararı geçerliliğini korur

ADR-0050 ile eklenen on-chain yüzeyi bu retle çöpe gitmez: mekanizma bağımsızlığı kapısını
geçen, dört yıl geçmişli ve PIT-güvenli bir yüzeydir. S-0007'nin reddi bu **tek** metriğin
(STH-SOPR) bu **tek** biçimde (30 günlük yüzdelik bandı, 24 saat ufuk) yön üretmediğini
söyler; yüzeyin tamamı hakkında bir şey söylemez.

## Sonuçlar ve sınırlar

- **`direction` runtime'da hâlâ null.** Kabul edilmiş setup yok; hiçbir yön yayınlanmıyor.
- **Beş ret bir başarısızlık değil, ölçümün çalıştığının kanıtıdır.** Beşinde de sonuç
  görülmeden kural donduruldu, beşinde de sonuç ne çıkarsa o kaydedildi. Bugüne kadar hiçbir
  eşik sonuca bakılarak değiştirilmedi ve hiçbir yön sonradan çevrilmedi.
- **Deneme sayacı büyüdü.** S-0007 beşinci denemedir; bir sonraki ailenin DSR cezası daha
  ağırdır. Bu, ön-kayıt disiplininin istenen etkisidir: her deneme bir sonrakini pahalılaştırır.
- **Bir sonraki aile için bilinen kısıt değişmedi:** mekanizma bağımsızlığı kapısı (ADR-0004
  §4) ürün sahibinin çağrısıdır ve uzun geçmişli yüzey hâlâ dardır. On-chain yüzeyinde
  STH-SOPR dışındaki seriler (whale bakiyeleri, likidasyonlar) aynı indiriciyle gelir ama
  her biri ayrı bir ön-kayıt ve ayrı bir deneme demektir.
