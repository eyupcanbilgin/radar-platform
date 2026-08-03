# SPEC.md — BTC Radar MCP
**Bitcoin Merkezli Kripto Piyasa Analiz MCP Sunucusu — Teknik Şartname v1.0**

| Alan | Değer |
|---|---|
| Proje sahibi | Eyüpcan |
| Tarih | 3 Ağustos 2026 |
| Durum | Taslak — Claude Code'a girdi olarak hazır |
| Çalışma adı | `btc-radar-mcp` (değiştirilebilir) |
| Temel girdiler | Kripto Piyasa Analiz Metodolojisi v1.0 (Eyüpcan), borsa-mcp mimari incelemesi (3 Ağu 2026), veri kaynağı fizibilite envanteri |

> **Yasal not:** Bu araç bir araştırma/karar-destek sistemidir. Yatırım tavsiyesi üretmez, emir göndermez, borsa hesabına bağlanmaz. Tüm çıktılar "yön/kırılganlık/güven skoru + gerekçe" formatındadır ve invalidasyon koşullarıyla birlikte sunulur.

---

## 1. Vizyon ve Kapsam

### 1.1 Tek cümlelik tanım
Metodoloji v1.0'daki çok katmanlı Bitcoin analiz çerçevesini, Claude'un (Desktop/Code/claude.ai) araç olarak çağırabileceği deterministik bir FastMCP sunucusuna dönüştürmek: **MCP veriyi toplar, normalize eder ve skorlar; LLM yorumlar ve raporlar.**

### 1.2 MVP kapsamı (Faz 1)
- Tek varlık: **BTC** (BTCUSDT perpetual + BTC-USD spot).
- 8 MCP aracı (Bölüm 4).
- Deterministik skorlama motoru: yön (−100..+100), kırılganlık (0..100), güven (0..100), rejim etiketi (Bölüm 5).
- Kaynak bazlı TTL önbelleği ve rate-limit koruması.
- stdio transport (uvx ile lokal çalıştırma). HTTP transport Faz 3.

### 1.3 Kapsam dışı (tüm fazlar için)
- Emir iletimi, borsa API key'i ile private endpoint kullanımı, bakiye erişimi.
- Fiyat/tarih tahmini iddiası.
- Ay fazı verisinin canlı skora katılması (metodoloji §3.8: %0 ağırlık; yalnız ayrı backtest modülü, Faz 3+).
- Kişiselleştirilmiş yatırım tavsiyesi üreten herhangi bir çıktı.

---

## 2. Veri Kaynağı Fizibilite Envanteri

Metodolojideki 8 katmanın MVP'de hangi kaynakla karşılandığı. **Doğrulama durumu:** ✅ = ücretsiz/anahtar gerektirmeyen public endpoint bilinen ve yaygın kullanımda; 🔑 = ücretsiz ama kayıt/anahtar gerekli; 💰 = paralı, MVP dışı; ⚠️ = implementasyon sırasında canlı doğrulama zorunlu (endpoint sözleşmesi değişmiş olabilir — Collector geliştirilirken ilk iş smoke test).

### 2.1 Türevler ve likidasyonlar (%25)
| Metrik | Kaynak | Endpoint (⚠️ canlı doğrula) | Erişim |
|---|---|---|---|
| Open Interest (anlık + tarihsel) | Binance Futures | `GET /fapi/v1/openInterest`, `GET /futures/data/openInterestHist` | ✅ |
| Funding rate (anlık + geçmiş) | Binance Futures | `GET /fapi/v1/premiumIndex`, `GET /fapi/v1/fundingRate` | ✅ |
| Long/Short hesap ve pozisyon oranları | Binance Futures | `GET /futures/data/globalLongShortAccountRatio`, `topLongShortPositionRatio` | ✅ |
| Taker buy/sell hacim oranı | Binance Futures | `GET /futures/data/takerlongshortRatio` | ✅ |
| Gerçekleşen likidasyonlar | Binance WS | `!forceOrder@arr` stream — **REST endpoint'i kaldırıldı**; MVP'de WS toplayıcı + yerel birikim VEYA bitcoin-data.com liquidation serisi | ⚠️ |
| Çapraz doğrulama (OI/funding) | Bybit v5 | `GET /v5/market/open-interest`, `/v5/market/funding/history` | ✅ |
| Liquidation map/heatmap | CoinGlass | — | 💰 MVP dışı. Skill "harita yok; gerçekleşen likidasyon + OI asimetrisiyle sınırlı analiz" diyecek. Güven katsayısı buna göre. |

### 2.2 On-chain (%25)
| Metrik | Kaynak | Not | Erişim |
|---|---|---|---|
| STH-SOPR, SOPR, MVRV, NUPL | bitcoin-data.com (BGeometrics) | Ücretsiz tier: ~8 istek/saat, 15/gün → **agresif önbellek zorunlu** (veri günlük; TTL ≥ 6 saat) | 🔑 |
| CDD / Exchange netflow-reserve | bitcoin-data.com | Aynı kaynak, aynı limit | 🔑 |
| 1.000+ BTC adres kohortu | bitcoin-data.com balance-address serileri; yoksa Faz 2'de blockchain.com charts API | ⚠️ metrik adı implementasyonda doğrulanacak | 🔑 |
| Whale accumulation heatmap | ChainExposed | API yok (HTML). MVP dışı; Faz 2'de scrape değerlendirilir | ⚠️ |
| CryptoQuant (CDD, SOPR birincil kaynağı) | — | 💰 MVP dışı. bitcoin-data.com ikamesi kullanılır; `source` alanında açıkça belirtilir, q katsayısı 0.75–0.9 bandında |

### 2.3 Spot ve bölgesel talep (%15)
| Metrik | Hesap | Kaynaklar | Erişim |
|---|---|---|---|
| Coinbase Premium | `(Coinbase BTC-USD − Binance BTCUSDT) / Binance × 100` — **kendimiz hesaplarız** | Coinbase Exchange `GET /products/BTC-USD/ticker` + Binance spot `GET /api/v3/ticker/price` | ✅ |
| Korea Premium | `(Upbit BTC-KRW / USDKRW − Binance BTCUSDT) / Binance × 100` | Upbit `GET /v1/ticker`, kur için açık FX kaynağı (implementasyonda seçilecek; ⚠️) | ✅/⚠️ |
| Spot taker CVD | Binance spot `GET /api/v3/trades` agregasyonu — Faz 2 | ✅ |

### 2.4 Genişlik ve rotasyon (%10)
| Metrik | Kaynak | Endpoint | Erişim |
|---|---|---|---|
| BTC dominance, toplam mcap | CoinGecko | `GET /api/v3/global` (ücretsiz tier ~30 çağrı/dk, demo key önerilir) | ✅/🔑 |
| Yükselen/düşen oranı (top 100) | CoinGecko | `GET /api/v3/coins/markets` üzerinden hesap | ✅ |
| ETH/BTC | Binance spot `ETHBTC` | ✅ |

### 2.5 Döngü ve duyarlılık (%10)
| Metrik | Kaynak | Endpoint | Erişim |
|---|---|---|---|
| Fear & Greed | Alternative.me | `GET https://api.alternative.me/fng/?limit=N` | ✅ |
| CBBI | ColinTalksCrypto | `GET https://colintalkscrypto.com/cbbi/data/latest.json` (tüm alt metrikler + composite; günlük) | ✅ |
| Bitcoin Magazine Pro F&G | — | Çift sayım grubu: Alternative.me ile TEK oy (metodoloji §5.5). Ayrı kaynak eklenmez. | — |

### 2.6 Haber ve katalizör (%10)
| Kaynak | Erişim | MVP kararı |
|---|---|---|
| CryptoPanic API | 🔑 ücretsiz tier | Faz 2. MVP'de haber katmanı MCP'ye girmez; skill LLM'e "haberi web_search ile doğrula, birincil kaynak iste" talimatı verir. Güven skoru haber kapsamı eksikliğini yansıtır. |
| CoinMarketCal API | 🔑 | Faz 2 |
| Rekt / Messari | scrape / 💰 | Faz 3 |

### 2.7 Yürütme/teknik bağlam (%5)
AGGR/CryptoMeter order-flow → gerçek zamanlı WS/tape işidir; MCP istek-yanıt modeline uymaz. MVP'de taker ratio + likidasyon verisi bu katmanın vekilidir. Faz 3'te ayrı bir "tape collector" servisi değerlendirilir.

### 2.8 Envanter sonucu
MVP ile metodolojinin **~%80 ağırlığı** ücretsiz kaynaklarla ölçülebilir. Ölçülemeyenler (liquidation map, whale heatmap, haber katmanı) skorda sıfır sayılmaz; **kapsam eksikliği olarak güven skorunu düşürür** (fail-closed ilkesi, metodoloji §1.3).

---

## 3. Mimari

### 3.1 Katman haritası (metodoloji §10.4 → kod)
```
[ LLM (Claude) + SKILL (analiz metodolojisi) ]
        │  MCP (stdio / Faz 3: HTTP)
        ▼
[ server.py — FastMCP araç tanımları ]          ← borsa-mcp: unified_mcp_server.py deseni
        │  shape() = strip_nulls + render_markdown
        ▼
[ core/router.py ]                               ← borsa-mcp: market_router deseni (ham dict döner)
        ▼
[ providers/  — kaynak başına bir sınıf ]        ← BaseProvider ABC
   binance_futures.py  binance_spot.py  bybit.py
   coinbase.py  upbit.py  coingecko.py
   alternative_me.py  cbbi.py  bitcoin_data.py
        ▼
[ core/normalizer.py ]  birim/venue/timestamp standardizasyonu
[ core/validator.py ]   şema, tazelik, duplicate, outlier (metodoloji §10.2)
[ core/features.py ]    rolling percentile, robust z-score (median/MAD), persistence
[ core/scoring.py ]     yön/kırılganlık/güven + rejim (metodoloji §5–6)
[ core/cache.py ]       kaynak bazlı TTL (diskcache)
[ config/weights.yaml ] katman ağırlıkları + eşikler — KODA GÖMÜLMEZ
```

### 3.2 Mimari kararlar (gerekçeli)
1. **Provider ABC:** `BaseProvider.fetch(metric, **params) -> RawObservation`. Kaynak değişimi (ör. bitcoin-data.com → CryptoQuant Faz 3'te) sadece yeni provider yazmak demektir. (borsa-mcp: Mynet→Borsapy geçişi deseni.)
2. **Router ham dict döndürür,** Pydantic doğrulaması provider çıkışında (giriş noktasında) yapılır — sıcak yolda tekrar doğrulama yok. (borsa-mcp `market_router` notu.)
3. **Skorlama MCP içinde, yorum LLM'de** (hibrit karar): d/r/q/f/u katsayıları ve tüm aritmetik `core/scoring.py`'de deterministik ve birim-testli. LLM'e skor + **bileşen dökümü** birlikte döner ki "neden 72?" cevaplanabilsin.
4. **Ağırlıklar ve eşikler `config/weights.yaml`'da.** Metodoloji sürümlenebilir; kod değişmeden ağırlık denemesi yapılabilir.
5. **Fail-loud parse:** parse edilemeyen sayı 0'a düşmez, hata fırlatır (borsa-mcp `parse_tcmb_number` dersi: sessiz 0 "değer sıfırdı" diye okunur).
6. **SSL doğrulaması asla global kapatılmaz** (borsa-mcp'deki anti-desen). Sorunlu kaynak olursa kaynak bazlı ve gerekçeli istisna.
7. **Önbellek TTL'leri kaynak gerçeğine göre:** on-chain (günlük veri) 6–12 saat; CBBI/F&G 1–6 saat; türev/premium 30–120 saniye. bitcoin-data.com'un 8 istek/saat limiti bu tasarımın zorlayıcı gerekçesidir.

### 3.3 Veri sözleşmesi — RawObservation (metodoloji §10.1)
Her provider çıkışı şu Pydantic modeline uyar:
```
timestamp_utc, retrieved_at_utc, asset, venue, metric, raw_value, unit,
window, source_group, source_url, quality(q: 0-1), notes
```
`freshness (f)` ve `independence (u)` katsayıları scoring aşamasında hesaplanır (f: veri yaşı / beklenen periyot; u: §5.5 çift sayım grupları).

---

## 4. MCP Araç Seti (8 araç)

Genel kurallar (hepsi borsa-mcp'den doğrulanmış desenler):
- Her parametre `Annotated[..., Field(description=..., examples=[...], ge/le=...)]`.
- **Araç başına daraltılmış Literal'lar:** araç şemada sadece gerçekten desteklediği değerleri ilan eder ("şema hatası > runtime hatası" ilkesi).
- Her docstring'de ≥2 somut çağrı örneği.
- `annotations={"readOnlyHint": True}` hepsi için (araçların hiçbiri yazma işlemi yapmaz).
- Dönüş: `shape()` → null temizliği + kompakt markdown/TSV. Kırpma yapılırsa `meta.truncated + guidance` eklenir.
- Hata: `classify_tool_error()` → LLM'e "sonraki adım" tavsiyeli ToolError (ör. 429 → "önbellekteki son değer X dakikalık; yeniden denemeden önce bekle").

| # | Araç | Ana parametreler | Kaynaklar | Not |
|---|---|---|---|---|
| 1 | `get_market_snapshot` | `detail: Literal["summary","full"]` | CoinGecko, Binance spot | Fiyat, 24s değişim, dominance, ETH/BTC, mcap, breadth özeti |
| 2 | `get_derivatives` | `venue: Literal["binance","bybit","all"]`, `metric: Literal["oi","funding","long_short","taker_ratio","all"]`, `window` | Binance/Bybit futures | Fiyat–OI–funding matrisinin (metodoloji §4.1) ham girdileri + tarihsel yüzdelik konumları |
| 3 | `get_liquidations` | `window: Literal["1h","6h","12h","24h"]` | WS birikimi veya bitcoin-data.com | Gerçekleşen long/short tasfiyeleri; "tahmini harita DEĞİL" notu yanıt metasında sabit |
| 4 | `get_onchain` | `metric: Literal["sth_sopr","sopr","cdd","netflow","reserve","mvrv","nupl","whale_cohort"]`, `lookback_days` | bitcoin-data.com | Önbellek zorunlu; yanıtta `retrieved_at` ve veri yaşı her zaman görünür |
| 5 | `get_premiums` | `premium: Literal["coinbase","korea","both"]` | Coinbase+Binance, Upbit | Hesaplama formülü yanıt metasında; anlık + kısa trend (son N gözlem) |
| 6 | `get_sentiment_cycle` | `include_history_days` | Alternative.me, CBBI | İki kaynak tek grupta döner; `independence_group` etiketiyle (çift sayım kuralı araca gömülü) |
| 7 | `compute_scores` | `horizon: Literal["daily","intraday","macro"]`, `explain: bool` | Tüm önbellek + gerekli taze çekimler | Yön/kırılganlık/güven + rejim + bileşen dökümü + eksik kapsam listesi. Güven<55 ise rejim etiketi "veri yetersiz" (metodoloji §6) |
| 8 | `get_health` | — | — | Kaynak erişilebilirliği, önbellek yaşları, son hatalar, rate-limit sayaçları. SDET aracı: sistem kendini test eder |

**Bilinçli sınır:** Araç sayısı 8'de tutulur (borsa-mcp'nin 81→28 konsolidasyon dersinin bir adım ötesi). Yeni ihtiyaç → önce mevcut araca parametre eklemek değerlendirilir, yeni araç son çare.

---

## 5. Skorlama Motoru

### 5.1 Formüller (metodoloji §5.1 birebir)
```
Yön        = 50 × Σ(wᵢ·dᵢ·qᵢ·fᵢ·uᵢ) / Σ(wᵢ·qᵢ·fᵢ·uᵢ)      → [−100, +100]
Kırılganlık = 50 × Σ(vᵢ·rᵢ·qᵢ·fᵢ) / Σ(vᵢ·qᵢ·fᵢ)            → [0, 100]
Güven      = 100 × ağırlıklı kapsam×kalite oranı              → [0, 100]
d ∈ {−2..+2}, r ∈ {0,1,2}, q,f,u ∈ [0,1]
```
- Metrik→d/r dönüşüm kuralları `config/signal_rules.yaml`'da tanımlanır (ör. "funding 90 günlük yüzdelik >95 VE OI 24s değişim >+%8 → r=2"). Kurallar rolling percentile/z-score ile göreli eşik kullanır, sabit sayı kullanmaz (metodoloji §5.2).
- Interaction kuralları desteklenir: bir metriğin puanı başka metriğin durumuna koşullanabilir (§5.2 adım 6).
- Rejim sınıflandırması §6 tablosu birebir: sağlıklı risk-on / kaldıraçlı coşku / sıkışmalı nötr / düzenli risk-off / deleveraging / birikim-kapitülasyon / veri yetersiz.

### 5.2 Skor çıktı sözleşmesi
`compute_scores` yanıtı şunları içerir: üç skor + bantlar, rejim etiketi, önceki çalıştırmaya göre delta (varsa), **her katmanın katkı dökümü** (w·d·q·f·u ürünleriyle), eksik/bayat kaynak listesi ve bunların güvene etkisi, kullanılan config sürümü (weights.yaml hash'i — izlenebilirlik).

---

## 6. Kalite, Test ve QA Stratejisi

1. **Birim testler (pytest):** scoring motoru altın-değer testleri (bilinen girdi → beklenen skor), normalizer sayı-parse testleri (TR/EN ayraç, bilimsel gösterim, null), çift-sayım grup testleri.
2. **Sözleşme testleri:** her provider için kaydedilmiş gerçek yanıt fixture'ları (`tests/fixtures/`); şema değişirse test kırılır (metodoloji §10.2 "tanım sürümü" kontrolünün otomasyonu).
3. **Canlı smoke test (`make smoke`):** tüm endpoint'lere 1'er istek, alan varlığı + tazelik kontrolü. CI'da günlük cron.
4. **Determinizm testi:** aynı fixture seti → her çalıştırmada bit-bit aynı skor.
5. **Rate-limit simülasyonu:** 429 senaryosunda önbelleğe düşüş ve güven skoru düşüşünün doğrulanması.
6. Kod incelemesi: her PR ayrı bir modele (Cursor/Codex) "MCP güvenlik + edge case" promptuyla incelettirilir (yazar ≠ incelemeci).

---

## 7. Yol Haritası

| Faz | İçerik | Bitti sayılma kriteri |
|---|---|---|
| **0 — İskelet** | Repo yapısı, uv, FastMCP hello-world, CI, config yükleme | `uvx --from . btc-radar` Claude Desktop'ta görünür, `get_health` çalışır |
| **1 — MVP** | 8 araç, 9 provider, cache, scoring, testler | `compute_scores` gerçek veriyle üç skor + rejim üretir; test coverage çekirdek modüllerde ≥%80; smoke yeşil |
| **2 — Derinlik** | Haber katmanı (CryptoPanic/CoinMarketCal), spot CVD, whale kohort iyileştirme, SKILL.md (analiz beyni) yazımı | Skill + MCP birlikte günlük tek-sayfa raporu (metodoloji §11.1) üretebiliyor |
| **3 — Yayın** | HTTP transport + /health, Docker, opsiyonel paralı kaynak adaptörleri, ay-fazı backtest modülü (ayrı, skor dışı) | Uzak sunucuda çalışır; README ile üçüncü kişi kurabilir |

---

## 8. Riskler ve Açık Sorular

| # | Risk/Soru | Plan |
|---|---|---|
| 1 | Endpoint sözleşmeleri değişmiş olabilir (özellikle Binance likidasyon, bitcoin-data.com metrik adları) | Faz 0'da ilk iş: canlı doğrulama scripti; SPEC ⚠️ işaretli satırlar güncellenir |
| 2 | bitcoin-data.com limiti (15/gün) on-chain kapsamı daraltabilir | Metrik önceliklendirme: STH-SOPR + CDD + netflow ilk üç; kalanlar günde 1 çekim |
| 3 | Türkiye'den bazı borsa API'lerine erişim kısıtı ihtimali | Provider'lara opsiyonel proxy config; Bybit yedeği |
| 4 | Skorun aşırı güven yaratması (kullanıcı psikolojisi) | Her `compute_scores` yanıtında invalidasyon + "araştırma aracı" notu; §11.3 dil kuralları skill'e gömülür |
| 5 | Korea premium için USDKRW kaynağı | İmplementasyonda seçilecek (açık FX API); seçim ADR olarak kaydedilir |
| 6 | WS likidasyon toplayıcısı MCP yaşam döngüsüne sığmayabilir (sunucu istek-bazlı) | MVP'de bitcoin-data.com serisiyle başla; WS toplayıcı ayrı süreç olarak Faz 2'de |

---

*Bu SPEC, CLAUDE.md ile birlikte okunur. Çelişki halinde SPEC işlevsel gereksinimlerde, CLAUDE.md kodlama pratiklerinde üstündür.*
