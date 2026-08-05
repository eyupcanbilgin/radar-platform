# 0018 — S-0004 Volatilite Rejimi Koşullandırmalı Trend Hipotez Değerlendirme Sonucu

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi (ADR karar kaydı) — S-0004 Hipotezi REDDEDİLDİ
- **İlgili:** S-0004 Hipotez Kartı, ADR-0014, ADR-0016, ADR-0017, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 2

## Bağlam

Faz 2'nin ikinci yönsel hipotezi olan S-0004 (Volatilite Rejimi Koşullandırmalı Trend), ön-kayıtlı 6 dondurulmuş kural ve 5 açıkça beyan edilen serbest parametre doğrultusunda sızıntısız Purged Walk-Forward altyapısı (`scripts/walk_forward_lib.py`) ve Baseline Değerlendiricisi (`scripts/baseline_evaluator.py`) kullanılarak Development döneminde (`2024-01-01T00:00:00Z` → `2026-08-04T00:00:00Z`) değerlendirilmiştir.

## Karar

1. **Ölçüm Yürütümü:**
   - **Tetikleyici ve Kapı:** 30 günlük rolling fiyat persentili ($P_{price}$) ve 14 günlük gerçekleşen volatilitenin 60 günlük persentili ($P_{vol}$). Yalnızca $\%20 \le P_{vol} \le \%80$ bandında işlem alınmış; aksi rejimlerde WAIT (0 getiri) üretilmiştir.
   - **Maliyet Senaryoları:** `config/costs.yaml` içerisindeki `realistic` (taker komisyon + 4 bps kayma) ve `taker_heavy` (taker komisyon + 8 bps kayma) senaryolarının her ikisi de raporlanmıştır.

2. **Sonuçlar ve Metrikler:**
   - **Toplam İşlem:** 454 işlem (28 valid Purged Walk-Forward fold).
   - **`realistic` Senaryo:** Kümülatif net getiri $R_{net} = -67.46\%$; işlem başı ortalama getiri $-21.76$ bps. `buy_and_hold` baseline ($-13.56\%$) ve `simple_trend` baseline ($+6.69\%$) gerisinde kalmıştır.
   - **`taker_heavy` Senaryo:** Kümülatif net getiri $R_{net} = -77.37\%$; işlem başı ortalama getiri $-29.74$ bps. `buy_and_hold` baseline ($-15.47\%$) ve `simple_trend` baseline ($-12.80\%$) gerisinde kalmıştır.
   - **İstatistiksel Anlamlılık:** Hareketli blok permütasyon testi p-değeri $p = 0.5487 \ge 0.05$ (rastgele süreçten ayırt edilemiyor).
   - **Fold Tutarlılığı:** Pozitif net getiri üreten fold oranı $\%39.3 < \%60$.

3. **Verdikt:**
   S-0004 hipotezi dondurulmuş ret kriterlerinin tamamını tetiklemiş ve **REDDEDİLMİŞTİR (REJECTED).**

4. **Provenance ve Kayıt:**
   Sonuç Experiment Registry `registry/experiments.jsonl` kütüğüne `E-20260805-110253-4c1b3c` kimliğiyle yazılmış; code SHA (`00100740410f`), dataset_snapshot (`6217119a82205871a3268b5badcc108f42ac1e2196f434f5a347156fc6549e28`) ve ortam parmak izi bağlanmıştır.

5. **Locked OOS Koruması:**
   Locked OOS (`2026-08-04T00:00:00Z`) açılmamıştır. Reddedilen hipotez için sonradan parametre oynatma, filtre ekleme veya Locked OOS testi yapılmayacaktır.

## Sonuçlar

Volatilite rejim kapısı eklenmesi trend sinyalinin maliyet sonrası net beklentisini iyileştirmemekte, aksine işlem sayısını artırarak maliyet yükünü ağırlaştırmaktadır. S-0004'ün reddedilmesi araştırma disiplininin ve baseline kıyaslama protokolünün çalıştığının açık kanıtıdır.
