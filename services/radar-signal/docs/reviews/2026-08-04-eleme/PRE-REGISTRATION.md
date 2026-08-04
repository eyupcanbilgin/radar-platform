# ÖN KAYIT (PRE-REGISTRATION) — Hipotez Eleme Tezgâhı

**Tarih:** 4 Ağustos 2026  
**Yazar:** Antigravity  
**Kapsam:** `radar-signal` hipotez kartları B, C, D, E, I, J, K, L, M ve kontrol olarak Kart A  
**Veri Aralığı:** `2024-01-01` → `2026-08-03` (Development & Extension pencereleri; 2026-08-04 sonrası TEMİZ OOS PENCERESİDİR — dokunulmaz).  
**Kural:** Bu kayıt testler çalıştırılmadan ÖNCE commit edilmiştir. Çalıştırmadan sonra bu listede herhangi bir test ekleme, çıkarma veya parametre değiştirme işlemi YAPILAMAZ.

---

## 1. Test Matrisi ve Hipotez Tanımları

### Kart A — Katılım ve likiditeyle koşullandırılmış momentum (Kontrol / Taban)
- **Mod:** Directional return (Long: +r, Short: −r)
- **Koşullar:** 15m return rank ≥ %80 (long) / ≤ %20 (short), 1h hacim medyan × 1.25, 1h high/low breakout, funding %5-95 ok.
- **Pencereler:** 20g (80 bar) ve 60g (240 bar)
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1, +2, +4, +8, +16 bar
- **Test sayısı:** 2 varlık × 2 pencere × 5 ufuk = **20 test**

### Kart B — Büyük intraday sıçrama sonrasında ortalamaya dönüş (Jump-reversal)
- **Mod:** Directional return (Contrarian: Şok yönünün tersine)
- **Koşullar:** 15m getiri |z-score| > 3 AND 15m hacim z-score > 3. (Likidasyonsuz kısım; spot/futures 15m verisiyle).
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1, +2, +4, +8, +16 bar
- **Test sayısı:** 2 varlık × 5 ufuk = **10 test**

### Kart C — Seans ilk aktif dönemden son aktif döneme momentum
- **Mod:** Directional return
- **Koşullar:** AB/ABD çakışma seansı (12:00–20:00 UTC). İlk 30m (12:00-12:30 UTC) hacmi rolling seans açılış hacimlerinin %70'inden büyükse, ilk 30m getirisinin yönünde pozisyon aç.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +2 bar (13:30 UTC), +4 bar (14:30 UTC), +16 bar (20:30 UTC - seans sonu)
- **Test sayısı:** 2 varlık × 3 ufuk = **6 test**

### Kart D — On beş dakikalık mum sınırı etkisi (1m verisiyle)
- **Mod:** Directional 1m return & Mum sınırı 1m getiri farkı (Sınır 1m: :59, :00, :14, :15, :29, :30, :44, :45 vs Diğer 1m)
- **Koşullar:** 1m futures verisi.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1m
- **Test sayısı:** 2 varlık × 1 ufuk = **2 test**

### Kart E — Aşırı funding sonrası volatilite genişlemesi
- **Mod:** Volatility Ratio (`RV_post_4h / RV_base_24h` ve `|r_fwd_4h| / |r_base_4h|`) & Directional return
- **Koşullar:** Saatlik funding rate z-score > 2.0 (veya üst %5 persentil).
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +4, +8, +16 bar
- **Test sayısı:** 2 varlık × 3 ufuk × 2 mod = **12 test**

### Kart I — Avrupa ve ABD açılışlarında aktivite ve volatilite genişlemesi
- **Mod:** Volatility Ratio (`RV_post_1h / RV_pre_1h`) & Directional ORB return
- **Koşullar:** Londra açılışı (08:00 UTC) ve NY açılışı (14:00 UTC). Açılış öncesi 1h high/low aralığının ilk 15m barında kırılması.
- **Varlıklar:** BTC, ETH
- **Seanslar:** Londra (08:00 UTC), NY (14:00 UTC)
- **Ufuklar:** +1, +2, +4 bar
- **Test sayısı:** 2 varlık × 2 seans × 3 ufuk × 2 mod = **24 test**

### Kart J — Hafta sonunda geleneksel seans etkisinin zayıflaması
- **Mod:** Volatility Ratio (Hafta sonu 1h RV / Hafta içi 1h RV) & Directional breakout return
- **Koşullar:** Cumartesi 00:00 UTC → Pazar 23:59 UTC dönemi.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1, +2, +4, +8 bar
- **Test sayısı:** 2 varlık × 4 ufuk × 2 mod = **16 test**

### Kart K — FOMC açıklaması sonrası volatilite ve getiri genişlemesi
- **Mod:** Volatility Ratio (`|r_post_1h| / |r_base_1h|`) & Directional ORB return (FOMC barı sonrası)
- **Koşullar:** `services/radar-signal/config/fomc_calendar.csv` dosyasındaki 21 adet resmî Fed duyuru zaman damgası.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1 bar (15m), +2 bar (30m), +4 bar (1h)
- **Test sayısı:** 2 varlık × 3 ufuk × 2 mod = **12 test**

### Kart L — Volatilite kümelenmesi ve rejim devamı
- **Mod:** Volatility Ratio (`RV_fwd_4h / RV_base_24h`) & Directional momentum return (yüksek vol rejiminde)
- **Koşullar:** `regime_ratio = RV_short (4 bar) / RV_long (96 bar)`. Oran > 80. persentil ise yüksek vol rejimi.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +4, +8, +16 bar
- **Test sayısı:** 2 varlık × 3 ufuk × 2 mod = **12 test**

### Kart M — Deribit settlement saati (08:00 UTC) aktivitesi
- **Mod:** Volatility Ratio (`RV_post_1h / RV_base_1h`) & Directional return
- **Koşullar:** Her gün 08:00 UTC settlement saati.
- **Varlıklar:** BTC, ETH
- **Ufuklar:** +1, +2, +4 bar
- **Test sayısı:** 2 varlık × 3 ufuk × 2 mod = **12 test**

---

## Kapsam Dışı ve Eksik Veri Etiketli Kartlar

1. **Kart G (Fiyat-Hacim-OI):** Open Interest (OI) verisi monorepoda bulunmadığı için **"TEST EDİLEMEDİ — VERİ EKSİK"** olarak etiketlenmiştir. Sentetik OI verisi uydurulmayacaktır.
2. **Kart N, O, P, Q:** Araştırma raporunda "düşük kanıt" etiketi taşıdığı ve doğrudan yönsel advantage üretmediği için ön eleme kapsamında test edilmeyecektir.

---

## 2. İstatistiksel Düzeltme Protokolü

- **Toplam Kayıtlı Test Sayısı (N):** 126 test.
- **Çoklu Test Düzeltmesi:** Benjamini-Hochberg (BH) False Discovery Rate (FDR) yöntemi uygulanacaktır ($q = 0.05$ ve $q = 0.10$ seviyeleri).
- **Raporlama:** Tüm testler için hem ham $p$ değeri (permütasyon testi, 2.000 permütasyon, seed `20260804`) hem de BH FDR düzeltmeli $p_{adj}$ değeri birlikte raporlanacaktır.
- **Maliyet Eşiği:** Yönsel adaylar için `realistic` senaryo gidiş-dönüş maliyet eşiği **17 bps** (BTC) ve **20 bps** (ETH) dikkate alınacaktır. Brüt beklenti bu eşiğin altındaysa istatistiksel olarak anlamlı olsa dahi YÖNSEL ADAY kabul edilmeyecektir.
