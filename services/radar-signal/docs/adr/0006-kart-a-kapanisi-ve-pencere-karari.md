# 0006 — Kart A'nın kapatılması ve rolling pencere kararı (Ç5)

* **Tarih:** 4 Ağustos 2026
* **Durum:** KABUL EDİLDİ
* **Kanıt:** `docs/reviews/2026-08-04-s0002/nabiz-analizi.md` (+ `.json` ham çıktı)

## Bağlam

İki çözülmemiş soru vardı:

1. **Ç5:** Kart A "son 60 günlük aynı saat dilimi dağılımı" diyor; S-0002b kodu
   `rolling(80)` yani 20 gün kullanıyordu. Kartı mı kodu mu düzeltmeli?
2. S-0002 ve S-0002b maliyet sonrası reddedilmişti, ama ret gerekçesi "maliyet küçük
   avantajı yedi" miydi, yoksa ortada avantaj hiç yok muydu? Bu ayrım yapılmadan
   Kart A'ya devam edilip edilmeyeceğine karar verilemezdi.

## Karar

**1. Kart A kapatılmıştır.** Sinyalin ölçülebilir öngörü gücü yoktur.

Nabız analizi (backtest değil; çıkış kuralı, stop, maliyet ve boyutlandırma
kaldırılarak yalnız ham forward getiri) 2024-01-01 → 2026-08-03 döneminde, BTC ve ETH'de,
+1/+2/+4/+8/+16 bar ufuklarında, iki pencere sürümüyle — **20 hücrenin 20'sinde**
yön düzeltmeli brüt ortalama **negatif**, isabet oranı **%50'nin altında**. Permütasyon
testinde sinyal, rastgeleden **anlamlı biçimde kötü** (p ≤ 0,034; çoğunda ≤ 0,005).

S-0002/S-0002b parametre ayarı, pencere değişikliği veya yeni çıkış kuralıyla
kurtarılmaya çalışılmayacaktır: sorun uygulamada değil, sinyalin kendisindedir.

**2. Ç5 kapandı — pencere KOD lehine, ama konu artık akademik.**

| | BTC +4bar | ETH +4bar | BTC +16bar | ETH +16bar |
|---|---|---|---|---|
| 20 gün (kod) | −1,88 | −3,59 | −3,21 | −3,32 |
| 60 gün (kart) | −2,58 | −4,98 | −4,48 | −3,97 |

Kartın dediği 60 günlük pencere her ölçümde daha kötü sonuç veriyor. Kodu karta
uydurmak durumu iyileştirmezdi. Kart A kapandığı için ne kod ne kart değiştirilecek;
**kayıt olarak** S-0002b'nin 20 günlük penceresi Kart A metninden bilinçli bir sapmadır
ve bu sapma sonucu iyileştirmiştir, kötüleştirmemiştir.

**3. Nabız testi kalıcı kapı olur.** Her yeni hipotez için **strateji kodu yazılmadan
önce** `scripts/signal_pulse.py` koşulur. Nabız testinden geçemeyen hipotez için
strateji yazılmaz.

Gerekçe: Kart A'da 3 strateji sürümü, 17 backtest koşusu, iki AI oturumu ve bir
bağımsız inceleme harcandı. Tek bir ölçüm (dakikalar) bunların hepsini baştan
gereksiz kılabilirdi.

## Sonuçlar

- `docs/hypotheses/S-0002.md` ve `S-0002b.md` nihai durum aldı; registry kayıtları
  (7× INVALID, 3× rejected) değişmez.
- SINYAL-SPEC §3.1'deki strateji tablosunda Kart A satırları KAPALI işaretlenir.
- Sıradaki hipotez Kart K (FOMC sonrası volatilite genişlemesi). Kart K **yön değil
  volatilite** iddiasıdır; nabız scriptine mutlak-getiri (yön-bağımsız) varyantı
  eklenmesi gerekir — bu, Kart K çalışması başlarken yapılacak ilk iştir.
- Ters yön (kırılmayı fade etmek) istatistiksel olarak anlamlı ama büyüklüğü −2…−5 bps,
  17 bps maliyet eşiğinin çok altında. Ayrı hipotez olarak AÇILMAZ.

## İtiraf

Bu analiz tek bir dönemde (2024-01 → 2026-08) ve tek bir borsada (Binance USDT-M)
yapıldı. Başka dönemde veya başka piyasa yapısında Kart A'nın davranışı farklı olabilir.
İddia, "Kart A evrensel olarak geçersizdir" değil; **"bu veri, bu dönem ve bu
operasyonelleştirme ile ölçülebilir bir öngörü gücü yoktur"**dur.
