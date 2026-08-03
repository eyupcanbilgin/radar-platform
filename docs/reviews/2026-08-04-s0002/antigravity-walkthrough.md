# S-0002 (Kart A — Hacim-Koşullu Intraday Momentum) Geliştirme ve Test Raporu

CR-002 yol haritasının 6. adımı olan **S-0002 (Hacim-Koşullu Intraday Momentum, Kart A)** stratejisinin geliştirilmesi, anti-desen kapı testleri, çoklu maliyet senaryoları altında backtest koşuları ve locked out-of-sample doğrulamaları tamamlanmıştır.

---

## 1. Operasyonelleştirme ve Yorumlar (Kart A)

Kart A'daki akademik bulgular (Wen, Bouri, Xu ve Zhao, 2022) 15 dakikalık mum yapısına ve CLAUDE.md ilkelerine uygun olarak şu şekilde göreli kurallara dönüştürülmüştür:

1. **Sabit Eşik Yasağı ve Göreli Rolling Eşikler:**
   - Sabit % getiri veya sabit BTC/ETH hacim eşikleri yerine son 20 günlük (1920 mum) geçmiş rolling dağılım üzerinden **göreli persentiller** kullanılmıştır.
   - 4 mumluk (1 saat) toplam getiri (`return_4bar`) past-window rolling `rank(pct=True)` ile %80 persentil eşiğiyle kıyaslanmıştır.
   - 1 saatlik toplam hacim (`volume_1h`) past-window `rolling().median()` değerinin 1.25 katı ile kıyaslanmıştır.
2. **Global Normalizasyon ve Look-Ahead Koruması:**
   - DataFrame geneline uygulanan `.min()`, `.max()`, `fit_transform()` tamamen engellenmiş; yalnızca `rolling(window=1920, min_periods=960)` kullanılmıştır.
   - `high_1h_max_shift1` ve `low_1h_min_shift1` göstergelerinde `shift(1)` uygulanarak geleceğe sızıntı sıfırlanmıştır.
3. **Gerekçe Mekanizması Etiketleri:**
   - Her giriş koşulu ayrı etiket taşımaktadır: `mom_vol_breakout_long` ve `mom_vol_breakout_short`.

---

## 2. Kabul Kapıları (DoD-4 Anti-Desen Testleri)

freqtrade 2026.7 araçlarıyla iki temel kabul kapısı çalıştırılmış ve başarıyla geçilmiştir:

- **Lookahead Bias Testi (`lookahead-analysis`):**
  - Komut: `.venv/Scripts/freqtrade lookahead-analysis --strategy S0002VolumeMomentum --timerange 20250101-20250401 -c config/config.dryrun.json`
  - Çıktı: **`has_bias = No`**, 20 sinyalin tamamında 0 biased entry, 0 biased exit.
- **Recursive Indicator Testi (`recursive-analysis`):**
  - Komut: `.venv/Scripts/freqtrade recursive-analysis --strategy S0002VolumeMomentum --timerange 20250101-20250201 -c config/config.dryrun.json`
  - Çıktı: *"No variance on indicator(s) found due to recursive formula"*, *"No lookahead bias on indicators found"*. Startup candle duyarlılık sapması $\pm\%0.025$ ile kabul sınırının altında kalmıştır.

---

## 3. Backtest Sonuçları Tablosu

Tüm koşular `scripts/bt.py` sarmalayıcısı ve `config/costs.yaml` maliyet matrisi ile, `--timeframe-detail 1m` ve muhafazakâr mum-içi simülatör altında gerçekleştirilmiştir.

| Dönem / Küme | Varlık | Maliyet Senaryosu | Efektif Fee | İşlem Sayısı | Maliyet Sonrası Net Getiri | Kazanma Oranı | Maks. Drawdown (DD) |
|---|---|---|---|---|---|---|---|
| **Geliştirme** (2024-01-01 → 2026-02-03) | BTC/USDT | `realistic` | 0.00085 | 4,599 | **−%89.91** | %21.4 | %89.91 |
| **Geliştirme** (2024-01-01 → 2026-02-03) | BTC/USDT | `taker_heavy` | 0.00125 | 3,231 | **−%89.94** | %18.5 | %89.94 |
| **Geliştirme** (2024-01-01 → 2026-02-03) | BTC/USDT | `stressed` | 0.00225 | 1,885 | **−%89.93** | %10.7 | %89.93 |
| **Locked OOS** (2026-02-03 → 2026-08-03) | BTC/USDT | `realistic` | 0.00085 | 1,311 | **−%28.82** | %18.1 | %28.82 |
| **Locked OOS** (2026-02-03 → 2026-08-03) | BTC/USDT | `taker_heavy` | 0.00125 | 1,311 | **−%38.94** | %13.8 | %38.94 |
| **Locked OOS** (2026-02-03 → 2026-08-03) | BTC/USDT | `stressed` | 0.00225 | 1,311 | **−%64.24** | %7.0 | %64.24 |
| **Bağımsız OOS** (2026-02-03 → 2026-08-03) | ETH/USDT | `realistic` | 0.00085 | 1,265 | **−%27.65** | %24.5 | %27.70 |

### Kıyas Tablosu (Locked OOS Dönemi: 2026-02-03 → 2026-08-03)
- **S-0002 Volume Momentum (BTC, realistic):** **−%28.82**
- **S-0001 Kontrol (BTC, realistic):** −%7.57
- **BTC Buy & Hold (Piyasa değişimi):** −%19.27

---

## 4. Mum-İçi Çıkış Oranı Analizi (Intra-candle Execution Drift)

- **S-0001 Kontrol Stratejisi Oranı:** %90.31
- **S-0002 Geliştirme Dönemi Oranı:** %89.32 (4599 işlemin 4108'i stop/trailing_stop ile mum içinde kapanmıştır)
- **S-0002 OOS Dönemi Oranı:** %90.46 (1311 işlemin 1186'sı mum içinde kapanmıştır)

**Değerlendirme:** 15m zaman dilimindeki intraday stratejilerde işlemlerin ~%90'ı mum kapanışını beklemeden bar ortasında stop seviyelerine çarpmaktadır. Bu durum, mum kapanış fiyatını esas alan ham backtestlerin aşırı derece pembe ve sahte sonuç üreteceğini; P0-5 kapsamındaki muhafazakâr mum-içi simülatörün zorunluluğunu kanıtlamaktadır.

---

## 5. Experiment Registry İstatistiği

- `scripts/bt.py` sarmalayıcısı üzerinden toplam **7 adet S-0002 deneyi** çalıştırılmış ve tamamı `registry/experiments.jsonl` kütüğüne işlenmiştir.
- DSR (Deflated Sharpe Ratio) için $N = 7$.
- Reddedilen varyant sayısı: **7 / 7** (%100 ret).

---

## 6. Hipotez Kartının Nihai Kararı (`docs/hypotheses/S-0002.md`)

**NİHAİ KARAR: GEREKÇELİ RET**

- **Neden?** Strateji, `SINYAL-SPEC` §1.3 kabul kriterlerinden **#1 (maliyet sonrası pozitif beklenti)** maddesini açıkça sağlayamamıştır.
- **Neden Başarısız Oldu?** Hacim ve getiri teyidi eklenmesine rağmen, 15m mum düzeyindeki intraday momentum son derece yüksek işlem sıklığı (günde ~6-7 işlem) üretmekte ve ortalama %0.20 civarındaki küçük brüt kârlar borsa komisyonları (8.5 - 12.5 bps) ve kayma maliyetleri altında tamamen erimektedir.
- **Sonuç:** Kart A hipotezi (katılım ve hacimle koşullandırılmış intraday momentum) bu biçimiyle bağımsız bir yönsel edge sunmamaktadır. Ret kaydı `docs/hypotheses/S-0002.md` dosyasına işlenmiştir.
