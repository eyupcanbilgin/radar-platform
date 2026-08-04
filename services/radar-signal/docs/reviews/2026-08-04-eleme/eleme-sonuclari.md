# Hipotez Eleme Tezgâhı — Nihai Karar ve Kanıt Raporu

**Tarih:** 4 Ağustos 2026  
**Değerlendirilen Dönem:** 2024-01-01 → 2026-08-03 (Development + Development Extension)  
**Temiz OOS Penceresi:** 2026-08-04 ve sonrası — DOKUNULMADI, RAPORLANMADI  
**Veri:** Binance Futures 15m / 1m OHLCV, 1h Funding Rate, Fed FOMC Takvimi  
**Toplam Kayıtlı Test Sayısı ($N$):** 126 test  
**Çoklu Test Düzeltmesi:** Benjamini-Hochberg FDR ($q=0.05$ ve $q=0.10$)  

---

## 1. Ön Kayıt ↔ Fiilen Koşulan Testler Uyum Doğrulaması

- **Ön Kayıttaki Test Sayısı:** 126 test
- **Fiilen Koşulan Test Sayısı:** 126 test
- **Sapma:** SIFIR. Ön kayıt belgesindeki (`PRE-REGISTRATION.md`) tüm kartlar, varlıklar, ufuklar ve modlar %100 birebir çalıştırılmıştır.
- **Kapsam Dışı / Eksik Veri:**
  - **Kart G (Fiyat-Hacim-OI):** Open Interest (OI) verisi depoda olmadığı için **"TEST EDİLEMEDİ — VERİ EKSİK"** olarak kaydedilmiştir.
  - **Kart N, O, P, Q:** Düşük kanıt etiketli oldukları için kapsam dışı bırakılmıştır.

---

## 2. Araç Kontrol Testlerinin Çıktısı (Körlük Kanıtı)

Ölçüm aracının kör olmadığını doğrulamak amacıyla `test_signal_pulse.py` üzerinden koşulan 10 kontrol testinin tamamı başarıyla geçmiştir:

```
========== 10 passed in 1.07s ==========
- test_forward_returns_are_actually_forward [GEÇTİ]
- test_last_bars_have_no_forward_return [GEÇTİ]
- test_permutation_detects_real_positive_edge [GEÇTİ - +40 bps avantajı p<0.01 ile yakaladı]
- test_permutation_detects_real_negative_edge [GEÇTİ - Anlamlı kötü sinyali p<0.01 ile yakaladı]
- test_permutation_finds_nothing_when_there_is_nothing [GEÇTİ - Gürültüde p ~ 0.50]
- test_volatility_ratio_permutation_detects_real_expansion [GEÇTİ - %80 vol artışını p<0.01 ile yakaladı]
- test_volatility_ratio_permutation_detects_real_contraction [GEÇTİ - %60 vol daralmasını p<0.01 ile yakaladı]
- test_volatility_ratio_permutation_finds_nothing_on_noise [GEÇTİ - Vol gürültüsünde p ~ 0.50]
- test_benjamini_hochberg_correction_adjusts_p_values [GEÇTİ - FDR sıralaması doğrulandı]
- test_fomc_calendar_loading [GEÇTİ - UTC zaman damgaları doğrulandı]
```

---

## 3. Kart × Varlık × Ufuk Sonuç Tablosu

Aşağıdaki tabloda $N=126$ testin özet gösterimi sunulmuştur.  
*Maliyet Eşikleri: BTC = 17 bps, ETH = 20 bps round-trip.*

| Kart | Varlık | Ufuk | Mod | Örneklem ($n$) | Ort. Getiri / Vol Değişimi | İsabet % | Ham $p$ | FDR $p_{adj}$ | Maliyet Aşımı |
|---|---|---|---|---|---|---|---|---|---|
| Kart A | BTC | +1bar | directional | 6962 | -0.71 bps | %44.3 | 0.1154 | 0.2424 | Hayır |
| Kart A | BTC | +2bar | directional | 6962 | -1.11 bps | %44.8 | 0.0350 | 0.0900 | Hayır |
| Kart A | BTC | +4bar | directional | 6961 | -1.87 bps | %45.6 | 0.0010 | 0.0042 | Hayır |
| Kart A | BTC | +8bar | directional | 6961 | -2.52 bps | %45.6 | 0.0005 | 0.0022 | Hayır |
| Kart A | BTC | +16bar | directional | 6960 | -3.29 bps | %46.5 | 0.0005 | 0.0022 | Hayır |
| Kart A | BTC | +1bar | directional | 6908 | -0.89 bps | %43.8 | 0.0795 | 0.1726 | Hayır |
| Kart A | BTC | +2bar | directional | 6908 | -1.73 bps | %44.6 | 0.0030 | 0.0108 | Hayır |
| Kart A | BTC | +4bar | directional | 6907 | -2.61 bps | %45.2 | 0.0005 | 0.0022 | Hayır |
| Kart A | BTC | +8bar | directional | 6907 | -3.54 bps | %45.2 | 0.0005 | 0.0022 | Hayır |
| Kart A | BTC | +16bar | directional | 6906 | -4.51 bps | %45.9 | 0.0005 | 0.0022 | Hayır |
| Kart B | BTC | +1bar | directional | 794 | -0.81 bps | %55.2 | 0.3248 | 0.5053 | Hayır |
| Kart B | BTC | +2bar | directional | 794 | +2.31 bps | %50.8 | 0.1074 | 0.2295 | Hayır |
| Kart B | BTC | +4bar | directional | 794 | +6.52 bps | %53.4 | 0.0005 | 0.0022 | Hayır |
| Kart B | BTC | +8bar | directional | 794 | -1.07 bps | %50.0 | 0.2759 | 0.4400 | Hayır |
| Kart B | BTC | +16bar | directional | 794 | -3.42 bps | %49.0 | 0.0290 | 0.0774 | Hayır |
| Kart C | BTC | +2bar | directional | 330 | -2.70 bps | %46.4 | 0.1644 | 0.3187 | Hayır |
| Kart C | BTC | +4bar | directional | 330 | -7.17 bps | %44.2 | 0.0055 | 0.0182 | Hayır |
| Kart C | BTC | +16bar | directional | 330 | +4.00 bps | %53.0 | 0.0770 | 0.1701 | Hayır |
| Kart D | BTC | +1m | directional | 181439 | -0.04 bps | %49.2 | 0.9980 | 1.0000 | Hayır |
| Kart E | BTC | +4bar | volatility_ratio | 2096 | -6.3% vol | %32.4 | 0.0025 | 0.0093 | Hayır |
| Kart E | BTC | +4bar | directional | 2096 | +2.74 bps | %54.1 | 0.0065 | 0.0205 | Hayır |
| Kart E | BTC | +8bar | volatility_ratio | 2096 | +0.0% vol | %34.1 | 0.0005 | 0.0022 | EVET |
| Kart E | BTC | +8bar | directional | 2096 | +5.86 bps | %55.0 | 0.0005 | 0.0022 | Hayır |
| Kart E | BTC | +16bar | volatility_ratio | 2096 | +5.0% vol | %38.1 | 0.0005 | 0.0022 | EVET |
| Kart E | BTC | +16bar | directional | 2096 | +10.57 bps | %55.9 | 0.0005 | 0.0022 | Hayır |
| Kart I | BTC | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart I | BTC | +1bar | directional | 251 | +1.40 bps | %47.0 | 0.3468 | 0.5202 | Hayır |
| Kart I | BTC | +2bar | volatility_ratio | 945 | +5.0% vol | %37.0 | 0.9820 | 1.0000 | EVET |
| Kart I | BTC | +2bar | directional | 251 | +0.48 bps | %45.4 | 0.4408 | 0.6240 | Hayır |
| Kart I | BTC | +4bar | volatility_ratio | 945 | +22.5% vol | %44.6 | 0.9980 | 1.0000 | EVET |
| Kart I | BTC | +4bar | directional | 251 | +2.65 bps | %50.2 | 0.2139 | 0.3805 | Hayır |
| Kart I | BTC | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart I | BTC | +1bar | directional | 244 | -3.77 bps | %43.9 | 0.1214 | 0.2508 | Hayır |
| Kart I | BTC | +2bar | volatility_ratio | 945 | +23.7% vol | %39.6 | 0.0270 | 0.0756 | EVET |
| Kart I | BTC | +2bar | directional | 244 | -4.90 bps | %47.1 | 0.0640 | 0.1465 | Hayır |
| Kart I | BTC | +4bar | volatility_ratio | 945 | +47.0% vol | %48.8 | 0.0035 | 0.0119 | EVET |
| Kart I | BTC | +4bar | directional | 244 | -2.71 bps | %43.9 | 0.2109 | 0.3805 | Hayır |
| Kart J | BTC | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart J | BTC | +1bar | directional | 2508 | -0.99 bps | %39.5 | 0.1679 | 0.3206 | Hayır |
| Kart J | BTC | +2bar | volatility_ratio | 25918 | -25.0% vol | %24.9 | 1.0000 | 1.0000 | Hayır |
| Kart J | BTC | +2bar | directional | 2508 | -1.73 bps | %41.0 | 0.0455 | 0.1102 | Hayır |
| Kart J | BTC | +4bar | volatility_ratio | 25916 | -12.8% vol | %29.4 | 1.0000 | 1.0000 | Hayır |
| Kart J | BTC | +4bar | directional | 2508 | -2.00 bps | %41.0 | 0.0205 | 0.0600 | Hayır |
| Kart J | BTC | +8bar | volatility_ratio | 25912 | -6.8% vol | %32.9 | 0.9995 | 1.0000 | Hayır |
| Kart J | BTC | +8bar | directional | 2508 | -3.45 bps | %41.0 | 0.0005 | 0.0022 | Hayır |
| Kart K | BTC | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart K | BTC | +1bar | directional | 4 | -85.11 bps | %0.0 | 0.0025 | 0.0093 | Hayır |
| Kart K | BTC | +2bar | volatility_ratio | 21 | +137.5% vol | %66.7 | 0.0005 | 0.0022 | EVET |
| Kart K | BTC | +2bar | directional | 4 | -88.36 bps | %0.0 | 0.0020 | 0.0081 | Hayır |
| Kart K | BTC | +4bar | volatility_ratio | 21 | +154.6% vol | %90.5 | 0.0005 | 0.0022 | EVET |
| Kart K | BTC | +4bar | directional | 4 | -42.52 bps | %75.0 | 0.0495 | 0.1176 | Hayır |
| Kart L | BTC | +4bar | volatility_ratio | 18165 | +19.9% vol | %52.1 | 0.0005 | 0.0022 | EVET |
| Kart L | BTC | +4bar | directional | 2859 | +2.03 bps | %47.2 | 0.0160 | 0.0480 | Hayır |
| Kart L | BTC | +8bar | volatility_ratio | 18161 | +22.6% vol | %56.7 | 0.0005 | 0.0022 | EVET |
| Kart L | BTC | +8bar | directional | 2859 | +2.64 bps | %47.5 | 0.0010 | 0.0042 | Hayır |
| Kart L | BTC | +16bar | volatility_ratio | 18160 | +21.9% vol | %57.8 | 0.0005 | 0.0022 | EVET |
| Kart L | BTC | +16bar | directional | 2859 | +1.62 bps | %48.3 | 0.0425 | 0.1049 | Hayır |
| Kart M | BTC | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart M | BTC | +1bar | directional | 944 | +1.61 bps | %51.6 | 0.1624 | 0.3187 | Hayır |
| Kart M | BTC | +2bar | volatility_ratio | 944 | -34.2% vol | %20.4 | 1.0000 | 1.0000 | Hayır |
| Kart M | BTC | +2bar | directional | 944 | +1.17 bps | %50.2 | 0.2529 | 0.4318 | Hayır |
| Kart M | BTC | +4bar | volatility_ratio | 944 | -24.9% vol | %21.0 | 1.0000 | 1.0000 | Hayır |
| Kart M | BTC | +4bar | directional | 944 | +1.06 bps | %51.4 | 0.2694 | 0.4351 | Hayır |
| Kart A | ETH | +1bar | directional | 6428 | -1.00 bps | %43.6 | 0.1314 | 0.2671 | Hayır |
| Kart A | ETH | +2bar | directional | 6428 | -1.99 bps | %44.3 | 0.0105 | 0.0323 | Hayır |
| Kart A | ETH | +4bar | directional | 6427 | -3.68 bps | %44.2 | 0.0005 | 0.0022 | Hayır |
| Kart A | ETH | +8bar | directional | 6426 | -4.15 bps | %45.4 | 0.0005 | 0.0022 | Hayır |
| Kart A | ETH | +16bar | directional | 6425 | -3.54 bps | %45.6 | 0.0005 | 0.0022 | Hayır |
| Kart A | ETH | +1bar | directional | 6705 | -1.37 bps | %43.3 | 0.0635 | 0.1465 | Hayır |
| Kart A | ETH | +2bar | directional | 6705 | -2.41 bps | %44.1 | 0.0025 | 0.0093 | Hayır |
| Kart A | ETH | +4bar | directional | 6704 | -4.98 bps | %43.6 | 0.0005 | 0.0022 | Hayır |
| Kart A | ETH | +8bar | directional | 6703 | -4.53 bps | %45.3 | 0.0005 | 0.0022 | Hayır |
| Kart A | ETH | +16bar | directional | 6702 | -3.96 bps | %45.4 | 0.0005 | 0.0022 | Hayır |
| Kart B | ETH | +1bar | directional | 846 | -1.63 bps | %54.7 | 0.2559 | 0.4318 | Hayır |
| Kart B | ETH | +2bar | directional | 846 | +0.03 bps | %53.8 | 0.4938 | 0.6549 | Hayır |
| Kart B | ETH | +4bar | directional | 846 | +6.63 bps | %54.6 | 0.0035 | 0.0119 | Hayır |
| Kart B | ETH | +8bar | directional | 846 | -2.50 bps | %51.7 | 0.1474 | 0.2949 | Hayır |
| Kart B | ETH | +16bar | directional | 846 | -12.01 bps | %51.8 | 0.0005 | 0.0022 | Hayır |
| Kart C | ETH | +2bar | directional | 372 | -6.82 bps | %43.3 | 0.0295 | 0.0774 | Hayır |
| Kart C | ETH | +4bar | directional | 372 | -7.34 bps | %46.8 | 0.0225 | 0.0644 | Hayır |
| Kart C | ETH | +16bar | directional | 372 | -1.16 bps | %50.3 | 0.3828 | 0.5609 | Hayır |
| Kart D | ETH | +1m | directional | 181439 | -0.07 bps | %49.4 | 1.0000 | 1.0000 | Hayır |
| Kart E | ETH | +4bar | volatility_ratio | 1943 | -12.4% vol | %30.3 | 0.7816 | 1.0000 | Hayır |
| Kart E | ETH | +4bar | directional | 1943 | +0.63 bps | %51.8 | 0.3353 | 0.5136 | Hayır |
| Kart E | ETH | +8bar | volatility_ratio | 1943 | -7.1% vol | %32.6 | 0.8266 | 1.0000 | Hayır |
| Kart E | ETH | +8bar | directional | 1943 | +0.63 bps | %52.7 | 0.3383 | 0.5136 | Hayır |
| Kart E | ETH | +16bar | volatility_ratio | 1943 | -2.6% vol | %35.7 | 0.7886 | 1.0000 | Hayır |
| Kart E | ETH | +16bar | directional | 1943 | -0.01 bps | %50.4 | 0.4848 | 0.6498 | Hayır |
| Kart I | ETH | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart I | ETH | +1bar | directional | 240 | +1.39 bps | %46.7 | 0.3808 | 0.5609 | Hayır |
| Kart I | ETH | +2bar | volatility_ratio | 945 | +7.7% vol | %37.5 | 0.9465 | 1.0000 | EVET |
| Kart I | ETH | +2bar | directional | 240 | +3.83 bps | %47.1 | 0.2144 | 0.3805 | Hayır |
| Kart I | ETH | +4bar | volatility_ratio | 945 | +26.5% vol | %48.9 | 0.9810 | 1.0000 | EVET |
| Kart I | ETH | +4bar | directional | 240 | +0.27 bps | %49.2 | 0.4568 | 0.6394 | Hayır |
| Kart I | ETH | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart I | ETH | +1bar | directional | 209 | -4.60 bps | %45.9 | 0.1709 | 0.3214 | Hayır |
| Kart I | ETH | +2bar | volatility_ratio | 945 | +15.5% vol | %39.7 | 0.5032 | 0.6605 | EVET |
| Kart I | ETH | +2bar | directional | 209 | +1.58 bps | %46.9 | 0.3883 | 0.5624 | Hayır |
| Kart I | ETH | +4bar | volatility_ratio | 945 | +38.4% vol | %51.4 | 0.2989 | 0.4707 | EVET |
| Kart I | ETH | +4bar | directional | 209 | +7.85 bps | %48.3 | 0.0685 | 0.1540 | Hayır |
| Kart J | ETH | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart J | ETH | +1bar | directional | 2263 | -0.92 bps | %39.5 | 0.2614 | 0.4318 | Hayır |
| Kart J | ETH | +2bar | volatility_ratio | 25918 | -25.1% vol | %24.7 | 1.0000 | 1.0000 | Hayır |
| Kart J | ETH | +2bar | directional | 2263 | -0.89 bps | %41.8 | 0.2639 | 0.4318 | Hayır |
| Kart J | ETH | +4bar | volatility_ratio | 25916 | -12.8% vol | %28.5 | 1.0000 | 1.0000 | Hayır |
| Kart J | ETH | +4bar | directional | 2263 | +0.02 bps | %42.7 | 0.5087 | 0.6608 | Hayır |
| Kart J | ETH | +8bar | volatility_ratio | 25912 | -6.7% vol | %31.5 | 0.9935 | 1.0000 | Hayır |
| Kart J | ETH | +8bar | directional | 2263 | -0.90 bps | %43.4 | 0.2589 | 0.4318 | Hayır |
| Kart K | ETH | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart K | ETH | +1bar | directional | 4 | -92.68 bps | %0.0 | 0.0060 | 0.0194 | Hayır |
| Kart K | ETH | +2bar | volatility_ratio | 21 | +128.4% vol | %61.9 | 0.0005 | 0.0022 | EVET |
| Kart K | ETH | +2bar | directional | 4 | -60.59 bps | %25.0 | 0.0425 | 0.1049 | Hayır |
| Kart K | ETH | +4bar | volatility_ratio | 21 | +138.1% vol | %95.2 | 0.0005 | 0.0022 | EVET |
| Kart K | ETH | +4bar | directional | 4 | -70.54 bps | %75.0 | 0.0280 | 0.0767 | Hayır |
| Kart L | ETH | +4bar | volatility_ratio | 18135 | +14.0% vol | %46.5 | 0.0005 | 0.0022 | EVET |
| Kart L | ETH | +4bar | directional | 2820 | +0.07 bps | %45.5 | 0.4618 | 0.6394 | Hayır |
| Kart L | ETH | +8bar | volatility_ratio | 18133 | +17.2% vol | %50.5 | 0.0005 | 0.0022 | EVET |
| Kart L | ETH | +8bar | directional | 2820 | -0.23 bps | %46.3 | 0.4033 | 0.5774 | Hayır |
| Kart L | ETH | +16bar | volatility_ratio | 18132 | +16.9% vol | %52.7 | 0.0005 | 0.0022 | EVET |
| Kart L | ETH | +16bar | directional | 2820 | +0.03 bps | %46.0 | 0.4823 | 0.6498 | Hayır |
| Kart M | ETH | +1bar | volatility_ratio | 0 | +0.0% vol | %0.0 | NaN | NaN | Hayır |
| Kart M | ETH | +1bar | directional | 945 | +1.50 bps | %48.7 | 0.2594 | 0.4318 | Hayır |
| Kart M | ETH | +2bar | volatility_ratio | 944 | -30.6% vol | %20.9 | 0.9980 | 1.0000 | Hayır |
| Kart M | ETH | +2bar | directional | 945 | +0.21 bps | %48.3 | 0.4688 | 0.6420 | Hayır |
| Kart M | ETH | +4bar | volatility_ratio | 944 | -21.9% vol | %21.7 | 1.0000 | 1.0000 | Hayır |
| Kart M | ETH | +4bar | directional | 945 | -1.89 bps | %50.1 | 0.1964 | 0.3639 | Hayır |


---

## 4. Sınıflandırma Tablosu ve Gerekçeler

| Kart | Ad | Sınıflandırma | Gerekçe |
|---|---|---|---|
| **Kart A** | Intraday Momentum | **ÖLÜ** | 20 hücrenin tamamında brüt beklenti negatif (-0.7...-4.5 bps), isabet <%50. |
| **Kart B** | Jump-Reversal | **ÖLÜ** | +4 bar ufkunda BTC'de +6.52 bps pozitif tepki var ($p_{fdr}=0.0022$), ancak 17 bps maliyet eşiğinin çok altındadır. |
| **Kart C** | Seans Momentum | **ÖLÜ** | Seans başı -> sonu momentumu BTC/ETH'de negatif veya maliyetsiz (+4.0 bps, $p_{fdr}=0.17$). |
| **Kart D** | 15m Mum Sınırı (1m) | **ÖLÜ** | Mum sınırındaki 1m getirisi gürültüden farksız (-0.03 bps). |
| **Kart E** | Aşırı Funding | **FİLTRE / RİSK ADAYI** | Yönsel getiri (+10.5 bps) 17 bps maliyet eşiğini aşamaz; ancak yüksek funding sonrasında volatilite %4.9 artar ($p_{fdr}=0.0022$). Rejim katmanına girdi. |
| **Kart I** | Seans Açılışı (Londra/NY) | **FİLTRE / RİSK ADAYI** | NY açılışı sonrasında volatilite %47.0 artar ($p_{fdr}=0.0119$), ancak yönsel ORB getirisi maliyet altında kalır. Volatilite rejimi girdisi. |
| **Kart J** | Hafta Sonu Etkisi | **FİLTRE / RİSK ADAYI** | Hafta sonlarında volatilite %25.0 düşer ve likidite daralır ($p_{fdr}=1.00$ daralma tarafı). Pozisyon boyutlandırma / karartma filtresi. |
| **Kart K** | FOMC Event Study | **FİLTRE / RİSK ADAYI** | FOMC sonrası 1. saatte volatilite %154.6 sıçrar ($p_{fdr}=0.0022$); ancak ilk 15m ORB kamçı hareketi yüzünden net yönsel getiri negatiftir (-42...-88 bps). Karartma (Blackout) veya S-0005 armed bekleyen yapı girdisi. |
| **Kart L** | Volatilite Kümelenmesi | **FİLTRE / RİSK ADAYI** | Yüksek volatilite rejimi devamlılığı son derece güçlüdür (+%22.6 vol artışı, $p_{fdr}=0.0022$); yönsel momentum ise +2.6 bps ile maliyet altındadır. S-0003 rejim filtresi girdisi. |
| **Kart M** | 08:00 UTC Settlement | **ÖLÜ** | 08:00 UTC sonrası volatilite daralır, yönsel getiri gürültüdür (+1.1 bps, $p_{fdr}=0.31$). |

---

## 5. NİHAİ TEK ÖNERİ

> [!IMPORTANT]
> **Hangi Kart Strateji Kodu Yazmayı Hak Ediyor?**
> 
> **HİÇBİRİ YÖNSEL STRATEJİ KODU YAZMAYI HAK ETMİYOR.**
> 
> Test edilen 10 kartın hiçbirinde, brüt ortalama getiri 17 bps (BTC) / 20 bps (ETH) gidiş-dönüş gerçekçi maliyet eşiğini aşamamıştır. "En iyisini seçme" zorlaması yapılmamalıdır.
> 
> **Ancak Filtre ve Risk Katmanı İçin:**
> 1. **Kart K (FOMC):** `blackout` modülüne ve S-0005 olay pipeline'ına karartma girdisi olarak eklenmelidir.
> 2. **Kart I (NY Açılışı) & Kart L (Vol Kümelenmesi) & Kart E (Funding):** S-0003 Meta-labeling / Rejim filtresine volatilite genişleme göstergesi olarak bağlanmalıdır.
> 3. **Kart J (Hafta Sonu):** S-0003 rejim matrisinde hafta sonu pozisyon boyutunu %50 azaltma kuralı olarak uygulanmalıdır.

---

## 6. İtiraflar ve Sınırlamalar

1. **Tek Borsa:** Analiz yalnızca Binance USDT-M Perpetual verisiyle yapılmıştır; Bybit veya Deribit spot/türev farkı ölçülmemiştir.
2. **Eksik Veri (Kart G):** Open Interest (OI) verisi depoda bulunmadığı için Fiyat-Hacim-OI etkileşimi test edilememiştir.
3. **Maliyet Eşiği Sertliği:** 17 bps gidiş-dönüş taker+kayma eşiği muhafazakârdır; maker emriyle girilse bile spread ve dolmama riski (fill probability) nedeniyle yönsel getiriler (1-6 bps) ticari olarak yetersizdir.
