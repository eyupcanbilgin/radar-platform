# 0017 — S-0003 Aşırı Settled Funding Hipotez Değerlendirme Sonucu

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi (ADR karar kaydı) — S-0003 Hipotezi REDDEDİLDİ
- **İlgili:** S-0003 Hipotez Kartı, ADR-0014, ADR-0016, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 2

## Bağlam

Faz 2'nin ilk yönsel hipotezi olan S-0003 (Aşırı Settled Funding Yönsel Reversal), ölçüm öncesi sıkılaştırılmış 5 dondurulmuş kural doğrultusunda sızıntısız Purged Walk-Forward altyapısı (`scripts/walk_forward_lib.py`) ve Baseline Değerlendiricisi (`scripts/baseline_evaluator.py`) kullanılarak Development döneminde (`2024-01-01T00:00:00Z` → `2026-08-04T00:00:00Z`) değerlendirilmiştir.

## Karar

1. **Ölçüm Yürütümü:**
   - **Tetikleyici ve Yön:** Settled funding 30 günlük rolling persentili $\ge \%95 \to$ SHORT, $\le \%5 \to$ LONG. Yayın-anı kuralına uyulmuş (`available_at <= karar_anı`), 24 saatlik etiket ufku (+24h) kullanılmıştır.
   - **Maliyet Senaryoları:** `config/costs.yaml` içerisindeki `realistic` (taker komisyon + 4 bps kayma) ve `taker_heavy` (taker komisyon + 8 bps kayma) senaryolarının her ikisi de raporlanmıştır.

2. **Sonuçlar ve Metrikler:**
   - **Toplam İşlem:** 316 işlem (28 valid Purged Walk-Forward fold).
   - **`realistic` Senaryo:** Kümülatif net getiri $R_{net} = -25.47\%$; işlem başı ortalama getiri $-6.69$ bps. `buy_and_hold` baseline ($-13.56\%$) ve `simple_trend` baseline ($+6.69\%$) gerisinde kalmıştır.
   - **`taker_heavy` Senaryo:** Kümülatif net getiri $R_{net} = -42.12\%$; işlem başı ortalama getiri $-14.68$ bps. `buy_and_hold` baseline ($-15.47\%$) ve `simple_trend` baseline ($-12.80\%$) gerisinde kalmıştır.
   - **İstatistiksel Anlamlılık:** Hareketli blok permütasyon testi p-değeri $p = 0.4083 \ge 0.05$ (rastgele süreçten ayırt edilemiyor).
   - **Fold Tutarlılığı:** Pozitif net getiri üreten fold oranı $\%39.3 < \%60$.

3. **Verdikt:**
   S-0003 hipotezi dondurulmuş ret kriterlerinin tamamını tetiklemiş ve **REDDEDİLMİŞTİR (REJECTED).**

4. **Provenance ve Kayıt:**
   Tek birincil ve geçerli kanıt kaydı `E-20260805-084135-e80d0f` kimlikli deneydir (code SHA: `d445953ef87f`, dataset_snapshot: `6217119a82205871a3268b5badcc108f42ac1e2196f434f5a347156fc6549e28`). Aynı koşunun mükerrer tekrarları olan `E-20260805-084344-eb6141` ve `E-20260805-084520-51861d` satırları `registry/verdict_events.jsonl` üzerinden `invalid` olarak işaretlenerek tekil kanıt kütüğü netleştirilmiştir.

5. **Locked OOS Koruması:**
   Locked OOS (`2026-08-04T00:00:00Z`) açılmamıştır. Reddedilen hipotez için sonradan parametre oynatma, filtre ekleme veya Locked OOS testi yapılmayacaktır.

## Sonuçlar

Settled funding oranının aşırı persentil değerleri tek başına kârlı bir yönsel avantaj (alpha) üretmemektedir. S-0003'ün reddedilmesi araştırma disiplininin çalıştığının, başarısız fikirlerin dürüstçe elendiğinin kanıtıdır.
