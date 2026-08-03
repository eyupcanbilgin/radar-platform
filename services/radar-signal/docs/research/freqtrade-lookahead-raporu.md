<!-- Kaynak: Gemini freqtrade-strategies analizi · Alınma: 3 Ağustos 2026 · CR-001/CR-6'nın kanıt kaynağı. Not: gitingest çıktısı kısmiydi; strateji .py dosyaları yakalanamadı, rapor lookahead_bias/readme.md üzerine kuruludur (bizim için asıl değerli kısım). -->

Sunulan dosya içerikleri ve Freqtrade mimari standartları doğrultusunda hazırlanan teknik yapısal analiz raporu aşağıdadır:

---

# FREQTRADE STRATEJİ MİMARİSİ VE ANTİ-DESEN ANALİZ RAPORU

## 1. Yapısal Desenler ve Katman Ayrımı (`populate_*`)

Freqtrade mimarisinde stratejiler, performans ve vektörleştirilmiş hesaplama (vectorized calculation) için 3 ana aşamaya ayrılır:

1. **`populate_indicators(dataframe, metadata)`**:
* Bütün teknik indikatörlerin (RSI, EMA, ATR vb.) tüm DataFrame üzerinde tek seferde hesaplandığı katmandır.
* Sinyal üretilmez, sadece veri sütunları (features) türetilir.

2. **`populate_entry_trend(dataframe, metadata)`** *(veya eski versiyonlarda `populate_buy_trend`)*:
* Indikatör sütunları kullanılarak mantıksal koşullar (`(dataframe['rsi'] < 30) & ...`) tanımlanır.
* Giriş sinyali için `dataframe.loc[koşul, 'enter_long'] = 1` şeklinde boolean bayraklar atanır.

3. **`populate_exit_trend(dataframe, metadata)`** *(veya eski versiyonlarda `populate_sell_trend`)*:
* Çıkış/kar al koşulları tanımlanır ve `dataframe.loc[koşul, 'exit_long'] = 1` atanır.

> **Repo Durumu:** Sunulan dosya seti içerisinde `populate_indicators`, `populate_entry_trend` veya `populate_exit_trend` metotlarını içeren somut bir Python strateji dosyası (`.py`) **repoda yok**.

---

## 2. Üst Zaman Dilimi Teyidi (Informative Pairs)

Üst zaman dilimi (Higher Timeframe - HTF) trendlerini stratejiye dahil ederken kullanılan standart desen:

* **`informative_pairs()`**: Stratejinin dinlemesi gereken ek çift ve zaman dilimlerini (örneğin 1h mumlar) Freqtrade çekirdeğine bildirir.
* **Hizalama ve Shift (Lookahead Önleme)**: Üst zaman diliminden alınan veri, alt zaman dilimine eklenirken (merge) henüz kapanmamış HTF mumunun verisi geçmişe sızmamalıdır. Bu nedenle veri 1 bar geriden (`.shift(1)`) çekilerek ana DataFrame'e `merge_informative_pair()` ile bağlanır.

> **Repo Durumu:** `informative_pairs` uygulayan veya üst zaman dilimini bağlayan herhangi bir Python strateji kodu sağlanan metinlerde **repoda yok**.

---

## 3. ATR Tabanlı Stop / Trailing Stop Mekanizması

Dinamik risk yönetimi için ATR (Average True Range) tabanlı stop-loss yapıları Freqtrade'de `custom_stoploss()` fonksiyonu üzerinden kurgulanır:

* `populate_indicators` içinde hesaplanan `atr` sütunu kullanılarak, pozisyona giriş fiyatı (`trade.open_rate`) ile güncel fiyat arasındaki ATR mesafesi hesaplanır.
* Pozisyon kâra geçtikçe stop seviyesi yukarı taşınır (Trailing ATR Stop).

> **Repo Durumu:** ATR tabanlı `custom_stoploss` veya dinamik trailing stop kod bloğu sağlanan metinlerde **repoda yok**.

---

## 4. Bilinen Hatalar ve Anti-Desenler (Lookahead Bias ve Kapanmamış Mum Riski)

Sağlanan `user_data/strategies/lookahead_bias/readme.md` dosyasında belgelendiği üzere, stratejilerdeki en kritik hatalar **Gelecek Verisi Sızıntısı (Lookahead Bias)** etrafında toplanmaktadır.

### A. Taranan Hatalar ve Somut Strateji Örnekleri

| Strateji Adı | Hatalı Kod / Yaklaşım | Hata Nedeni (Anti-Pattern) | Referans Dosya |
| --- | --- | --- | --- |
| **`DevilStra`** | `normalize()` metodunda `.min()` ve `.max()` kullanımı | Tüm DataFrame'in mutlak min/max değerlerini alır. Strateji, henüz gerçekleşmemiş gelecek fiyat uç değerlerini bilerek geçmişi normalize eder. | `user_data/strategies/lookahead_bias/readme.md` |
| **`GodStraNew`** | `normalize()` metodunda `.min()` ve `.max()` kullanımı | `DevilStra` ile aynı şekilde tüm serinin min/max değerlerini gelecekten çeker. | `user_data/strategies/lookahead_bias/readme.md` |
| **`Zeus`** | `trend_ichimoku_base` ve `trend_kst_diff` indikatörlerinde `.min()` / `.max()` kullanımı | İndikatör ölçeklendirmesinde tüm veri kümesinin uç değerlerini kullanarak sinyalleri geleceğe göre mükemmelleştirir. | `user_data/strategies/lookahead_bias/readme.md` |
| **`wtc`** | `MinMaxScaler().fit_transform(x)` kullanımı | `sklearn`'in `MinMaxScaler` aracı tüm diziyi (`x`) alarak serinin mutlak min/max değerlerini hesaplar. Geçmiş mumlar, gelecekteki zirve ve diplere göre ölçeklenir. | `user_data/strategies/lookahead_bias/readme.md` |

### B. Global Normalizasyon Riski (Özet)

Bir veri serisini normalize ederken **tüm DataFrame** üzerinden min/max almak (Global Normalization), backtest sırasında %100'e yakın sahte başarı oranları üretir ancak canlı ticarette çöker.

* **Doğru Yapı:** Normalizasyon yapılacaksa sadece o ana kadar olan geçmiş verileri kapsayan hareketli pencere (**Rolling Window / `rolling().min()`**) kullanılmalıdır.

### C. Kapanmamış Mum (Unclosed Candle / Repaint) Riski

* Canlı işlem sırasında henüz süresi dolmamış (kapanmamış) mumun `close` fiyatı sürekli değişir.
* Strateji kapanmamış mumun değerine dayanarak `enter_long` veya `exit_long` sinyali üretirse; mum kapanırken fiyat değiştiğinde sinyal kaybolabilir (Repaint).
* Freqtrade'de bunun önüne geçmek için `process_only_new_candles = True` konfigürasyonu kullanılır ve indikatör kontrolleri mum kapanış fiyatına göre yapılır.

> **Repo Durumu:** Kapanmamış mum kullanımıyla ilgili hatalı Python strateji kodu (`.py`) sağlanan dosyalar arasında **repoda yok**.

---

## ÖZET / AÇIK SORULAR

* **Gelecek Sızıntısı (Lookahead Bias):** Repodaki örneklerde ana sızıntı kaynağı indikatör veya veri ölçeklendirmede `MinMaxScaler` ve global `.min()/.max()` fonksiyonlarının kullanılmasıdır (`user_data/strategies/lookahead_bias/readme.md`).
* **Kod Eksikliği:** Repoda sadece strateji talep şablonları (`strategy_request.md`), PR şablonu ve lookahead bias klasörünün `readme.md` açıklaması bulunmaktadır. Kod düzeyinde `populate_*` uygulamaları, `informative_pairs` fonksiyonları ve `custom_stoploss` kod örnekleri **repoda yer almamaktadır**.
