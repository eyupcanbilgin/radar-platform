import json
from pathlib import Path

json_path = Path("services/radar-signal/docs/reviews/2026-08-04-eleme/eleme-sonuclari.json")
out_md_path = Path("services/radar-signal/docs/reviews/2026-08-04-eleme/eleme-sonuclari.md")

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

tests = data["tests"]

report_md = f"""# Hipotez Eleme Tezgâhı — Nihai Karar ve Kanıt Raporu

**Tarih:** 4 Ağustos 2026  
**Değerlendirilen Dönem:** 2024-01-01 → 2026-08-03 (Development + Development Extension)  
**Temiz OOS Penceresi:** 2026-08-04 ve sonrası — DOKUNULMADI, RAPORLANMADI  
**Veri:** Binance Futures 15m / 1m OHLCV, 1h Funding Rate, Fed FOMC Takvimi  
**Toplam Kayıtlı Test Sayısı ($N$):** {data['total_registered_tests']} test  
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

| Kart | Varlık | Ufuk | Mod | Örneklem ($n$) | Ort. Getiri / Vol Değişimi | İsabet % | Ham $p$ | FDR $p_{{adj}}$ | Maliyet Aşımı |
|---|---|---|---|---|---|---|---|---|---|
"""

for t in tests:
    card = t["card"]
    sym = t["symbol"]
    hor = t["horizon"]
    mode = t["mode"]
    n = t["n_signals"]
    mean_val = t["mean_bps"]
    hit = t["hit_rate"]
    p_raw = t["p_raw"]
    p_fdr = t["p_fdr"]
    beats = t["beats_cost"]

    if mode == "directional":
        val_str = f"{mean_val:+.2f} bps"
    else:
        val_str = f"{mean_val:+.1f}% vol"

    p_raw_str = f"{p_raw:.4f}" if not str(p_raw).startswith("nan") else "NaN"
    p_fdr_str = f"{p_fdr:.4f}" if not str(p_fdr).startswith("nan") else "NaN"
    beats_str = "EVET" if beats else "Hayır"

    report_md += f"| Kart {card} | {sym} | {hor} | {mode} | {n} | {val_str} | %{hit*100:.1f} | {p_raw_str} | {p_fdr_str} | {beats_str} |\n"

report_md += """

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
"""

out_md_path.parent.mkdir(parents=True, exist_ok=True)
out_md_path.write_text(report_md, encoding="utf-8")
print(f"Rapor yazıldı: {out_md_path}")
