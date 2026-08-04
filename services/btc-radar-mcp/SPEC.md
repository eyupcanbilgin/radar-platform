# SPEC.md — BTC Radar MCP
**Bitcoin Merkezli Kripto Piyasa Analiz MCP Sunucusu — Teknik Şartname v1.2**

> v1.2 (4 Ağu 2026): İlk gerçek Binance USD-M provider, PIT collector, fail-closed exact-hour
> context publisher ve `get_derivatives` dar dilimi uygulandı. v1.1 → git geçmişi.

| Alan | Değer |
|---|---|
| Proje sahibi | Eyüpcan |
| Tarih | 3 Ağustos 2026 |
| Durum | Uygulamada — Faz 1a veri taşıması tamam, skorlama hazır değil |
| Çalışma adı | `btc-radar-mcp` (değiştirilebilir) |
| Temel girdiler | Kripto Piyasa Analiz Metodolojisi v1.0 (Eyüpcan), borsa-mcp mimari incelemesi (3 Ağu 2026), veri kaynağı fizibilite envanteri |

> **Yasal not:** Bu araç bir araştırma/karar-destek sistemidir. Yatırım tavsiyesi üretmez,
> emir göndermez, borsa hesabına bağlanmaz. Skor üretilemediğinde bunu null skorlar ve açık
> blocker'larla bildirir; eksik veriyi nötr sinyal gibi göstermez.

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

**Mevcut Faz 1a dilimi:** Binance BTCUSDT anlık mark/funding/OI provider'ı,
`get_derivatives`, append-only PIT toplama ve `decision-context/v1` exact-hour publisher
uygulanmıştır.

**Mevcut Faz 1b dilimi (ADR-0005):** Tarihsel settled funding ve saatlik OI backfill'i,
PIT-güvenli seri okuma, yeterli-geçmiş kapısı ve iki **kırılganlık** feature'ı
(`funding_stress`, `oi_buildup`) uygulanmıştır. `fragility` artık gerçek veriden üretilir;
**direction ve rejim üretimi bilinçli olarak kapalı kalır** — kabul edilmiş yönsel setup ve
çok katmanlı kapsam yoktur. Context bu nedenle `direction: null` ve
`direction_rules_unavailable` blocker'ı ile yayınlanır.

### 1.3 Kapsam dışı (tüm fazlar için)
- Emir iletimi, borsa API key'i ile private endpoint kullanımı, bakiye erişimi.
- Fiyat/tarih tahmini iddiası.
- Ay fazı verisinin canlı skora katılması (metodoloji §3.8: %0 ağırlık; yalnız ayrı backtest modülü, Faz 3+).
- Kişiselleştirilmiş yatırım tavsiyesi üreten herhangi bir çıktı.

---

## 2. Veri Kaynağı Fizibilite Envanteri

Metodolojideki 8 katmanın MVP'de hangi kaynakla karşılandığı. **Doğrulama durumu:** ✅ = ücretsiz/anahtar gerektirmeyen public endpoint bilinen ve yaygın kullanımda; 🔑 = ücretsiz ama kayıt/anahtar gerekli; 💰 = paralı, MVP dışı; ⚠️ = implementasyon sırasında canlı doğrulama zorunlu (endpoint sözleşmesi değişmiş olabilir — Collector geliştirilirken ilk iş smoke test).

### 2.1 Türevler ve likidasyonlar (%25)
| Metrik | Kaynak | Endpoint (canlı doğrulandı: 3 Ağu 2026, `scripts/verify_endpoints.py`) | Erişim |
|---|---|---|---|
| Open Interest (anlık + tarihsel) | Binance Futures | `GET /fapi/v1/openInterest`, `GET /futures/data/openInterestHist` | ✅ |
| Funding rate (anlık + geçmiş) | Binance Futures | `GET /fapi/v1/premiumIndex`, `GET /fapi/v1/fundingRate` | ✅ |
| Long/Short hesap ve pozisyon oranları | Binance Futures | `GET /futures/data/globalLongShortAccountRatio`, `topLongShortPositionRatio` | ✅ |
| Taker buy/sell hacim oranı | Binance Futures | `GET /futures/data/takerlongshortRatio` | ✅ |
| Gerçekleşen likidasyonlar | bitcoin-data.com | `GET /v1/btc-liquidations` (+`-1h`, `-1d` varyantları; alanlar: `totalLiquidationsUsd`, `longLiquidationsUsd`, `shortLiquidationsUsd`) — **MVP kararı bu seri**. Binance REST'in kaldırıldığı doğrulandı (`/fapi/v1/allForceOrders` → 404, 3 Ağu 2026); WS `!forceOrder@arr` toplayıcı ihtiyacı düştü (Risk 6 çözüldü) | ✅ anahtarsız doğrulandı |
| Çapraz doğrulama (OI/funding) | Bybit v5 | `GET /v5/market/open-interest`, `/v5/market/funding/history` | ✅ |
| Liquidation map/heatmap | CoinGlass | — | 💰 MVP dışı. Skill "harita yok; gerçekleşen likidasyon + OI asimetrisiyle sınırlı analiz" diyecek. Güven katsayısı buna göre. |

### 2.2 On-chain (%25)
| Metrik | Kaynak | Not | Erişim |
|---|---|---|---|
| STH-SOPR, SOPR, MVRV, NUPL | bitcoin-data.com (BGeometrics) | `GET /v1/sth-sopr`, `/v1/sopr`, `/v1/mvrv`, `/v1/nupl` (+`/last` son gözlem; sözleşme: `{d, unixTs, <metrik>}`). Ücretsiz tier: ~8 istek/saat, 15/gün → **agresif önbellek zorunlu** (veri günlük; TTL ≥ 6 saat). Üretim host: `api.bitcoin-data.com` (`bitcoin-data.com/v1` de çalışır); OpenAPI: `api.bgeometrics.com/v3/api-docs` | ✅ anahtarsız doğrulandı (3 Ağu 2026); **opsiyonel API key tasarımı:** `BTC_RADAR_BITCOIN_DATA_API_KEY` env tanımlıysa provider header'a ekler (limit artırımı için), yoksa anahtarsız devam |
| CDD / Exchange netflow-reserve | bitcoin-data.com | `GET /v1/cdd`, `/v1/exchange-netflow-btc`, `/v1/exchange-reserve-btc` — aynı kaynak, aynı limit | ✅ |
| 1.000+ BTC adres kohortu | bitcoin-data.com | Tek "1000+" serisi YOK; **bant-bazlı saklama**: `/v1/balance-addr-10K-1K-BTC` ve `/v1/balance-addr-10K-BTC` bantları ayrı ayrı kaydedilir, "1K+" toplaması scoring anında yapılır (ham bant verisi korunur, toplama kuralı config'de). Alternatif kesitler: `/v1/address-cohorts`, `/v1/wallet-bands`. blockchain.com yedeğine gerek kalmadı | ✅ metrik adları doğrulandı |
| Whale accumulation heatmap | ChainExposed | API yok (HTML). MVP dışı; Faz 2'de scrape değerlendirilir | ⚠️ |
| CryptoQuant (CDD, SOPR birincil kaynağı) | — | 💰 MVP dışı. bitcoin-data.com ikamesi kullanılır; `source` alanında açıkça belirtilir, q katsayısı 0.75–0.9 bandında |

### 2.3 Spot ve bölgesel talep (%15)
| Metrik | Hesap | Kaynaklar | Erişim |
|---|---|---|---|
| Coinbase Premium | `(Coinbase BTC-USD − Binance BTCUSDT) / Binance × 100` — **kendimiz hesaplarız** | Coinbase Exchange `GET /products/BTC-USD/ticker` + Binance spot `GET /api/v3/ticker/price` | ✅ |
| Korea Premium | `(Upbit BTC-KRW / USDKRW − Binance BTCUSDT) / Binance × 100` | Upbit `GET /v1/ticker` ✅ · USDKRW kaynağı SEÇİLDİ (ADR-0002): birincil `open.er-api.com/v6/latest/USD`, yedek `api.frankfurter.dev/v1/latest` (ECB); üçü de 3 Ağu 2026'da canlı doğrulandı | ✅ |
| Spot taker CVD | Binance spot `GET /api/v3/trades` agregasyonu — Faz 2 | ✅ |

### 2.4 Genişlik ve rotasyon (%10)
| Metrik | Kaynak | Endpoint | Erişim |
|---|---|---|---|
| BTC dominance, toplam mcap | CoinGecko | `GET /api/v3/global` (ücretsiz tier ~30 çağrı/dk, demo key önerilir; anahtarsız doğrulandı 3 Ağu 2026). **Kesinti yedeği: CoinPaprika fallback provider** (`GET /v1/global`; CoinGecko 429/5xx'te devreye girer, `source` alanında belirtilir, q katsayısı düşürülür) | ✅/🔑 |
| Yükselen/düşen oranı (top 100) | CoinGecko | `GET /api/v3/coins/markets` üzerinden hesap | ✅ |
| ETH/BTC | Binance spot `ETHBTC` | ✅ |

### 2.5 Döngü ve duyarlılık (%10)
| Metrik | Kaynak | Endpoint | Erişim |
|---|---|---|---|
| Fear & Greed | Alternative.me | `GET https://api.alternative.me/fng/?limit=N` | ✅ |
| CBBI | ColinTalksCrypto | `GET https://colintalkscrypto.com/cbbi/data/latest.json` (tüm alt metrikler + composite; günlük). Canlı ölçüm: ~3,5 sn gecikme (en yavaş kaynak) → provider timeout ≥10 sn, TTL ≥6 saat | ✅ |
| Bitcoin Magazine Pro F&G | — | Çift sayım grubu: Alternative.me ile TEK oy (metodoloji §5.5). Ayrı kaynak eklenmez. | — |

### 2.6 Haber ve katalizör (%10)
| Kaynak | Erişim | MVP kararı |
|---|---|---|
| CryptoPanic API | 🔑 ücretsiz tier | Faz 2. MVP'de haber katmanı MCP'ye girmez; skill LLM'e "haberi web_search ile doğrula, birincil kaynak iste" talimatı verir. Güven skoru haber kapsamı eksikliğini yansıtır. |
| CoinMarketCal API | 🔑 | Faz 2 |
| sharpe.ai ücretsiz katmanı | 🔑 | Fizibilite doğrulama kuyruğunda (CR-002 küçük maddesi): kapsam/limit/sözleşme incelenmeden karar verilmez |
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
[ core/features.py ]    rolling percentile + yeterli-geçmiş kapısı (UYGULANDI, ADR-0005)
[ core/components.py ]  feature → d/r dönüşümü; d şu an daima None (yön kuralı yok)
[ core/backfill.py ]    sayfalı geçmiş toplama (funding ileri, OI geriye)
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
timestamp_utc, retrieved_at_utc, available_at_utc, asset, venue, metric, raw_value,
unit, window, source_group, source_url, quality(q: 0-1), notes
```
`available_at_utc` = verinin sistemce **ilk bilinebildiği** an (CR-002 P0-1). Provider yayın gecikmesini biliyorsa doldurur; boşsa `retrieved_at_utc` kullanılır (muhafazakâr taraf). `freshness (f)` ve `independence (u)` katsayıları scoring aşamasında hesaplanır (f: veri yaşı / beklenen periyot, eğim `weights.yaml → freshness`; u: §5.5 çift sayım grupları).

### 3.4 Point-in-time depo ve değişmez snapshot (CR-002 P0-1 — UYGULANDI)
```
[ core/store.py ]     append-only PIT deposu (SQLite)
   satır alanları: event_time, available_at, ingested_at, provider,
                   schema_version, payload_hash + gözlem alanları
   read_as_of(as_of) → YALNIZ available_at ≤ as_of satırları; revizyonlar
                       ayrı satır olarak korunur (revision_history)
[ core/snapshot.py ]  compute_snapshot() + SnapshotStore (değişmez)
   snapshot alanları: snapshot_id, as_of, data_cutoff_at, computed_at, skorlar,
                      feature_version, scoring_version, weights_hash, input_digest,
                      content_hash, stale_sources, missing_layers, breakdown
```
- `snapshot_id` girdilerin deterministik türevidir; `computed_at` içerik hash'ine girmez.
- Depo, kaydın taşıdığı `content_hash`'e güvenmez — gövdeden yeniden hesaplayıp doğrular.
- Tam aynı bilgi-zamanı retry'ı idempotenttir; farklı `available_at` ayrı kanıt satırıdır.
  Böylece out-of-order ingest ve A→B→A revizyon dizisi yazma sırasından bağımsız korunur.
- Snapshot ID/hash yalnız yazmada değil okumada da doğrulanır; `data_cutoff_at` v0.2'den
  itibaren içerik hash'ine dahildir, v0.1 geçmişi legacy doğrulamayla okunabilir kalır.
- **`get_as_of` vardır, `get_latest` YOKTUR:** aynı saatte birden fazla snapshot varsa örtük
  seçim yapılmaz; `snapshot_id` açıkça seçilmelidir.
- Kabul testi karşılandı: 100 replay → bit-bit özdeş skor/gerekçe (`tests/test_snapshot.py`). Ayrıntı: ADR-0003.

### 3.5 Signal servis sınırı — `decision-context/v1`

MCP'nin `RegimeSnapshot` çıktısı monorepo kökündeki
`contracts/decision-context/v1/schema.json` sözleşmesiyle signal servisine taşınır. İlk
dar kapsam `BTCUSDT · Binance USDT perpetual · 1h · paper`dır. MCP yalnız bağlam üretir;
`LONG/SHORT/WAIT` seçmez. Zorunlu veri eksiği `directional_decision_allowed=false` ve
blocker listesiyle fail-closed taşınır. Ortak fixture iki servisin testinde doğrulanır;
HTTP transport bu sözleşmenin dışındadır ve daha sonraki fazda uygulanır.

Faz 1a publisher yolu
`var/decision-context/v1/BTCUSDT/1h/YYYY/MM/DD/HH.json` biçimindedir. Yayın same-filesystem
temp + `fsync` + atomik no-overwrite hard-link ile yapılır. Mevcut exact-hour artifact hiçbir
zaman değiştirilmez. Kurallar boşken snapshot gerçek PIT girdilerinin digest'ini taşır ama
skorları null, confidence'ı 0 ve yön kapısı kapalıdır (ADR-0004).

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
| 2 | `get_derivatives` | **Faz 1a:** `metric: Literal["mark_price","funding_rate","open_interest","all"]`; gelecekte venue/window genişler | Binance USD-M futures | **Dar dilim uygulandı:** PIT zamanlı anlık ham gözlemler. Tarihsel funding/OI serisi `btc-radar-producer backfill` ile PIT'e toplanır ve kırılganlık yüzdelikleri saatlik context'te yayınlanır (ADR-0005); bu araç skor döndürmez. Bybit henüz yok |
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
- Metrik→d/r dönüşüm kuralları `config/signal_rules.yaml`'da tanımlanır. Kurallar rolling percentile ile göreli eşik kullanır, sabit sayı kullanmaz (metodoloji §5.2). **Uygulandı (ADR-0005):** `funding_stress` ve `oi_buildup` kuralları yüzdelik bantlarıyla r üretir.
- **Yeterli geçmiş şartı (ADR-0005):** her feature `min_samples`, `min_span_days` ve `max_gap_seconds` taşır. Şart sağlanmazsa feature üretilmez ve context'e `feature_unavailable:<feature>:<neden>` blocker'ı yazılır — eksik geçmiş nötr skora dönüşmez.
- **`d` boş olabilir:** yön iddiası taşımayan bileşen (`d=None`) yön paydasına girmez; hiçbir kural yön iddia etmiyorsa `direction` null kalır ve `direction_rules_unavailable` blocker'ı yazılır. Yönsel kural kabul edilmiş bir setup olmadan açılmaz.
- Interaction kuralları §5.2 adım 6'da öngörülür fakat **henüz uygulanmadı**: kırılganlık formülünde bağımsızlık terimi (u) olmadığı için aynı feature'ı etkileşim kuralında tekrar saymak skoru şişirir. Önce CR-002 P1-1 iki kademeli toplaması gerekir (ADR-0005).
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
| **1a — Veri taşıması (tamamlandı)** | Binance mark/funding/OI provider, PIT collector, immutable exact-hour context | Gerçek public fixture'lar, no-look-ahead, hash/ID doğrulama, atomik no-overwrite ve fail-closed consumer sözleşmesi testli |
| **1b — Geçmiş ve kırılganlık (tamamlandı)** | Settled funding + saatlik OI backfill, PIT seri okuma, yeterli-geçmiş kapısı, `funding_stress`/`oi_buildup` | Gerçek veriyle fragility üretiliyor; yetersiz geçmiş blocker yazıyor; digest kullanılan geçmişi kapsıyor; direction hâlâ null (ADR-0005) |
| **1 — MVP** | 8 araç, 9 provider, cache, scoring, testler | `compute_scores` gerçek veriyle üç skor + rejim üretir; test coverage çekirdek modüllerde ≥%80; smoke yeşil |
| **2 — Derinlik** | Haber katmanı (CryptoPanic/CoinMarketCal), spot CVD, whale kohort iyileştirme, SKILL.md (analiz beyni) yazımı | Skill + MCP birlikte günlük tek-sayfa raporu (metodoloji §11.1) üretebiliyor |
| **3 — Yayın** | HTTP transport + /health, Docker, opsiyonel paralı kaynak adaptörleri, ay-fazı backtest modülü (ayrı, skor dışı) | Uzak sunucuda çalışır; README ile üçüncü kişi kurabilir |

---

## 8. Riskler ve Açık Sorular

| # | Risk/Soru | Plan |
|---|---|---|
| 1 | ~~Endpoint sözleşmeleri değişmiş olabilir~~ **YAPILDI (3 Ağu 2026):** doğrulama scripti yazıldı, 24 kontrol koşuldu, ⚠️ satırlar güncellendi (bkz. §2 tabloları + ADR-0002) | Günlük smoke CI'da sürer (`.github/workflows/smoke.yml`) |
| 2 | bitcoin-data.com limiti (15/gün) on-chain kapsamı daraltabilir | Metrik önceliklendirme: STH-SOPR + CDD + netflow ilk üç; kalanlar günde 1 çekim |
| 3 | Türkiye'den bazı borsa API'lerine erişim kısıtı ihtimali — **3 Ağu 2026 itibarıyla gözlenmedi** (Binance spot+futures, Bybit, Upbit, Coinbase erişilebilir); madde açık kalır | Provider'lara opsiyonel proxy config; Bybit yedeği |
| 4 | Skorun aşırı güven yaratması (kullanıcı psikolojisi) | Her `compute_scores` yanıtında invalidasyon + "araştırma aracı" notu; §11.3 dil kuralları skill'e gömülür |
| 5 | ~~Korea premium için USDKRW kaynağı~~ **YAPILDI:** open.er-api.com birincil, frankfurter.dev yedek — ADR-0002 | Smoke scripti üç adayı izlemeye devam eder |
| 6 | ~~WS likidasyon toplayıcısı~~ **ÇÖZÜLDÜ (3 Ağu 2026):** bitcoin-data.com hazır likidasyon serisi doğrulandı; WS toplayıcıya MVP'de gerek yok | İhtiyaç doğarsa Faz 2'de ayrı süreç olarak yeniden değerlendirilir |

---

*Bu SPEC, CLAUDE.md ile birlikte okunur. Çelişki halinde SPEC işlevsel gereksinimlerde, CLAUDE.md kodlama pratiklerinde üstündür.*
