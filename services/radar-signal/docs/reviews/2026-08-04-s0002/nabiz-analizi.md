# Kart A Nabız Teşhisi — Sinyalin öngörü gücü var mı?

**Tarih:** 4 Ağustos 2026 · **Script:** `scripts/signal_pulse.py` · **Ham çıktı:** `nabiz-analizi.json`
**Dönem:** 2024-01-01 → 2026-08-03 (90.720 bar/varlık) · **Permütasyon:** 5.000, seed 20260804

## Ne yapıldı

Backtest değil. S-0002b'nin giriş koşulları birebir yeniden üretildi ve **çıkış kuralı,
stop, maliyet, boyutlandırma katmanlarının hepsi kaldırıldı**. Geriye tek soru kaldı:

> Sinyal barından sonraki ham fiyat hareketi, rastgele bir bardan farklı mı?

Yön düzeltmeli brüt getiri (long: +r, short: −r) +1/+2/+4/+8/+16 barda ölçüldü.
Taban dağılım: aynı dönemin tüm barları, **rastgele bar + rastgele yön** (sinyallerle
aynı long oranı). Yön ataması zaman konumundan bağımsız yapıldı — ilk sürümde barlar
zaman sırasına göre bölündüğü için dönem trendi tabana sızıyordu, düzeltildi.
Boş dağılımın ortalaması ≈ 0.00 bps çıkması bu düzeltmenin doğrulamasıdır.

**Maliyet eşiği:** `realistic` senaryoda gidiş-dönüş ≈ **17 bps**. Brüt ortalama bunun
altındaysa sinyal istatistiksel olarak anlamlı olsa bile ticari olarak ölüdür.

## Sonuçlar

Tüm değerler baz puan (bps). `p(kötü)` = sinyalin rastgeleden anlamlı biçimde KÖTÜ
olma olasılığının permütasyon testi.

### BTC

| Ufuk | n | Ort. | Medyan | İsabet | Boş ort. | p(kötü) |
|---|---|---|---|---|---|---|
| **20 gün pencere (koddaki)** ||||||
| +1 bar (15dk) | 6.915 | −0,71 | −3,60 | %44,3 | 0,00 | 0,011 |
| +2 bar (30dk) | 6.915 | −1,10 | −4,43 | %44,8 | 0,01 | 0,005 |
| +4 bar (1sa) | 6.914 | −1,88 | −4,73 | %45,6 | −0,02 | 0,001 |
| +8 bar (2sa) | 6.914 | −2,46 | −6,26 | %45,6 | −0,01 | 0,004 |
| +16 bar (4sa) | 6.913 | −3,21 | −6,94 | %46,5 | 0,00 | 0,004 |
| **60 gün pencere (Kart A'nın dediği)** ||||||
| +1 bar | 6.895 | −0,88 | −4,18 | %43,8 | 0,00 | 0,004 |
| +2 bar | 6.895 | −1,71 | −5,15 | %44,6 | −0,01 | 0,001 |
| +4 bar | 6.894 | −2,58 | −5,18 | %45,2 | 0,00 | 0,000 |
| +8 bar | 6.894 | −3,55 | −6,51 | %45,3 | −0,01 | 0,000 |
| +16 bar | 6.893 | −4,48 | −8,33 | %46,0 | −0,02 | 0,000 |

### ETH

| Ufuk | n | Ort. | Medyan | İsabet | p(kötü) |
|---|---|---|---|---|---|
| **20 gün** |||||
| +1 bar | 6.382 | −1,01 | −6,02 | %43,5 | 0,011 |
| +2 bar | 6.382 | −1,97 | −6,81 | %44,3 | 0,000 |
| +4 bar | 6.381 | −3,59 | −8,29 | %44,1 | 0,000 |
| +8 bar | 6.380 | −4,00 | −9,74 | %45,4 | 0,001 |
| +16 bar | 6.379 | −3,32 | −12,42 | %45,6 | 0,034 |
| **60 gün** |||||
| +1 bar | 6.689 | −1,38 | −6,40 | %43,3 | 0,001 |
| +2 bar | 6.689 | −2,42 | −7,16 | %44,1 | 0,000 |
| +4 bar | 6.688 | −4,98 | −9,34 | %43,6 | 0,000 |
| +8 bar | 6.687 | −4,53 | −10,07 | %45,3 | 0,000 |
| +16 bar | 6.686 | −3,97 | −13,54 | %45,4 | 0,012 |

**20 hücrenin 20'sinde ortalama negatif. 20'sinde de isabet oranı %50'nin altında.
Hiçbiri 17 bps maliyet eşiğine yaklaşmıyor — hepsi sıfırın yanlış tarafında.**

## Kırılımlar (+4 bar = 1 saat)

### UTC saat dilimi

| Dilim | BTC 20g | BTC 60g | ETH 20g | ETH 60g |
|---|---|---|---|---|
| 00–05 | −2,08 | −3,02 | −1,19 | −3,21 |
| 06–11 | −2,12 | −2,70 | −2,59 | −2,84 |
| 12–17 | **+0,77** | −0,56 | −2,49 | −5,08 |
| 18–23 | −4,43 | −4,26 | **−8,11** | **−8,80** |

Tek pozitif hücre BTC 12–17 UTC (ABD seansı) ve +0,77 bps — maliyetin yirmide biri.
En kötü dilim her iki varlıkta 18–23 UTC.

### Volatilite rejimi (ATR persentil terzili)

| Rejim | BTC 20g | BTC 60g | ETH 20g | ETH 60g |
|---|---|---|---|---|
| Düşük | −0,75 | −1,42 | −1,85 | −4,75 |
| Orta | −0,16 | −2,04 | **+2,42** | +0,44 |
| Yüksek | −2,92 | −3,05 | −6,96 | −7,97 |

Sinyallerin çoğu (%60'ı) yüksek volatilite rejiminde üretiliyor ve en kötü sonuç orada.
ETH orta-vol hücresi +2,42 bps ile tek anlamlı pozitif, yine de maliyetin altında ve
diğer üç sütunda tekrarlanmıyor — tek hücrelik gürültü olarak okunmalı.

## Ç5 kapanışı: 20 gün mü, 60 gün mü?

**60 gün (Kart A'nın dediği) her ölçümde 20 günden DAHA KÖTÜ:**

| | BTC +4bar | ETH +4bar | BTC +16bar | ETH +16bar |
|---|---|---|---|---|
| 20 gün | −1,88 | −3,59 | −3,21 | −3,32 |
| 60 gün | −2,58 | −4,98 | −4,48 | −3,97 |

Kodu karta uydurmak (60 güne çıkarmak) sonucu iyileştirmiyor, kötüleştiriyor.
Karar ve gerekçe: **ADR-0006**.

## Anti-desen kapıları (DoD-4 borcu kapatıldı)

freqtrade 2026.7, 4 Ağustos 2026, S-0002b:

- **`lookahead-analysis`** (20250101-20250401, 20 sinyal): **has_bias = No** — 0 biased
  entry, 0 biased exit, 0 biased indicator. **TEMİZ.**
- **`recursive-analysis`** (20250101-20250201): "No lookahead bias on indicators found",
  fakat **ısınma duyarlılığı sıfır değil**:

| Gösterge | 399 mum | 999 mum | 1920 (stratejinin ayarı) |
|---|---|---|---|
| `return_4bar_pct_rank` | −16,955% | +3,300% | **−0,452%** |
| `volume_1h_median` | −11,159% | −4,822% | **+0,177%** |
| `atr`, `volume_1h` | ~0,000% | ~0,000% | ~0,000% |

**Yorum:** Saat-dilimi koşullaması her saat grubuna günde yalnız 4 bar verdiği için
rank/medyan yavaş ısınıyor. `startup_candle_count=1920`'de bile gösterge tam ısınmış
değerinden ~%0,45 sapıyor. Bu bir look-ahead değil, **ısınma bağımlılığıdır**: test
penceresinin başındaki gösterge değerleri, öncesinde ne kadar geçmiş olduğuna bağlı.
Kıyas: S-0001 ±0,000%, S-0002 ±0,025%, S-0002b **−0,452%** — üçünün en duyarlısı.

Nabız analizi tam dönem üzerinde ve bol ısınmayla koşulduğu için bu bulgudan etkilenmez,
ancak kısa pencereli koşularda dikkate alınmalıdır. Kart notlarına eklendi.

## HÜKÜM

**Kart A'nın 15m operasyonelleştirmesinin ölçülebilir bir öngörü gücü YOKTUR.**

Sinyal yalnızca "avantajsız" değil, incelenen dönemde **rastgeleden istatistiksel olarak
anlamlı biçimde kötüdür** (20 hücrenin 20'sinde negatif ortalama, p(kötü) ≤ 0,034;
çoğunda ≤ 0,005). Yani hacim teyitli kırılma barından sonra fiyat, kırılma yönünün
TERSİNE hafif bir eğilim gösteriyor.

Bu, önceki ret kararlarını da yeniden yorumlatıyor: S-0002b'nin −17 bps işlem beklentisi
"maliyet küçük avantajı yedi" değil, **"zaten negatif olan brüt beklentinin üstüne maliyet
bindi"** demekti. Brüt beklenti +4 bar ufkunda −1,9 (BTC) / −3,6 (ETH) bps.

Ters yönde işlem (kırılmayı fade etmek) istatistiksel olarak anlamlı görünüyor ama
büyüklük −2 ile −5 bps arasında; 17 bps maliyet eşiğinin çok altında. **Ticari olarak
o da ölüdür** ve ayrı bir hipotez olarak açılması önerilmez.

### Ne yapılmalı

1. **Kart A KAPATILIR.** S-0002 ve S-0002b nihai olarak reddedilmiştir; parametre ayarı,
   pencere değişikliği veya yeni çıkış kuralıyla kurtarma denemesi yapılmamalıdır —
   sorun uygulamada değil, sinyalin kendisinde.
2. **Yöntem kalıcıdır.** `signal_pulse.py` bundan sonra her hipotez için **strateji
   yazılmadan ÖNCE** koşulmalıdır. Kart A'da 3 strateji sürümü, 17 backtest koşusu ve
   iki AI oturumu, tek bir ölçümle baştan elenebilecek bir sinyal için harcandı.
3. **Sıradaki hipotez** araştırma raporundaki öncelik sırasına göre Kart K (FOMC sonrası
   volatilite genişlemesi) olmalı — ve önce nabız testinden geçmeli. Not: Kart K yön
   değil volatilite iddiasıdır; nabız scriptinin mutlak-getiri varyantı gerekecek.
