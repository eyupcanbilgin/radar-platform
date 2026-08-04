# ADR 0007 — Spot OHLCV, spot/perp basis ve order-book spread/depth toplayıcıları

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0004, ADR-0005, ADR-0006, Hedefe Geliştirme Planı Faz 1

## Bağlam

Faz 1'in "ilk çekirdek veri aileleri" listesinde (SPEC §1.2) üç madde açıktı: spot
fiyat/hacim, spot-perpetual basis, spread ve sınırlı order-book depth. Funding ve OI
(ADR-0004/0005) zaten toplanıyordu. Bu paket geriye kalan üçünü PIT'e taşır.

Kapsam bilinçli olarak **ADR-0004'ün (Faz 1a) aynı ölçeğindedir**: gerçek Binance verisini
append-only PIT deposuna yazmak. Yeni bir kırılganlık feature'ı, yeni bir `signal_rules.yaml`
kuralı, yeni bir MCP aracı veya tarihsel backfill **açmaz**. Direction ADR-0005'ten beri null;
bu paket onu değiştirmez.

## Kararlar

### 1. Spot OHLCV: yalnız kapanmış mum, klines'tan

`BinanceSpotProvider.fetch("ohlcv_1h")` `GET api.binance.com/api/v3/klines?interval=1h&limit=2`
çeker. Canlı ölçüm (5 Ağustos 2026): `limit=2` isteğinde son satır çoğu zaman henüz kapanmamış
mumdur (`closeTime` gelecekte). Karar mumunun kapanışından önce OHLC'sini "biliniyormuş gibi"
kullanmak look-ahead olurdu (ADR-0004'ün mark-price gerekçesiyle aynı ilke). Bu yüzden
`closeTime > retrieved_at` olan satırlar atılır ve kalan en yeni (tam kapanmış) satır kullanılır;
hiçbiri kapanmamışsa fail-loud hata verilir — sessizce "en son gelen satırı kullan" davranışı
yanlış bir mum seçebilirdi.

Beş gözlem üretilir: `spot_open`, `spot_high`, `spot_low`, `spot_close`, `spot_volume`
(`venue=binance_spot`, `source_group=spot`). `timestamp_utc` mumun `openTime`'ıdır (mumun
kimliği); `available_at_utc = max(retrieved_at, closeTime)` mumun ne zaman **bilinebilir**
olduğunu taşır — ikisi kasıtlı olarak farklı alanlardır.

### 2. Spot/perp basis Binance içinde hesaplanır, cross-exchange bağımsız değildir

`fetch("spot_perp_basis")` canlı `GET api.binance.com/api/v3/ticker/price` (spot) ile
`BinanceFuturesProvider.fetch("mark_price")` (perp) sonucunu birleştirip
`basis = (spot − mark) / mark × 100` hesaplar. Coinbase/Korea premium (SPEC §2.3, "kendimiz
hesaplarız") ile aynı desen: MCP kendi hesaplamasını yapar, borsadan hazır bir basis alanı
beklemez.

Fark şu: iki bacak da **aynı borsadandır** (Binance spot + Binance USD-M). SPEC §5.5'in çift
sayım / bağımsızlık mantığı burada kırılganlık lehine yorumlanır: bu, cross-exchange bir
arbitraj sinyali değil, Binance'ın kendi spot-perp makasının kırılganlık-benzeri bir gözlemidir.
Bu yüzden `source_group="derivatives"` seçildi — `funding_stress`/`oi_buildup` (ADR-0005) ile
aynı aile, ayrı bir "spot_regional" değil. `ticker/price` zaman alanı taşımadığından
(canlı doğrulandı) o bacağın zamanı `retrieved_at`'tir (RawObservation'ın muhafazakâr
varsayılanı, ADR-0003).

`BinanceSpotProvider` bir `futures_provider` enjekte edilebilir (`__init__` parametresi):
`producer.py._collect()` aynı `BinanceFuturesProvider` örneğini paylaşarak basis bacağı için
ikinci bir `premiumIndex` isteği açmaz.

### 3. Spread/depth perp order book'undan, sabit sayfa boyutuyla

`BinanceFuturesProvider`'a (yeni dosya değil — aynı host, aynı "anlık" semantik, CLAUDE.md
kural 9'un provider'lara uygulanışı) `order_book` metriği eklendi:
`GET fapi.binance.com/fapi/v1/depth?limit=20`. Perp defteri seçildi çünkü kararın enstrümanı
BTCUSDT perpetual'dır (spot defteri değil). Üç gözlem üretir: `order_book_spread_bps`
(`(best_ask−best_bid)/mid × 10000`), `order_book_depth_bid_usd`,
`order_book_depth_ask_usd` (çekilen 20 seviyenin price×qty toplamı).

Depth "mid'in ±X%'i içindeki" gibi icat edilmiş bir bant değildir — CLAUDE.md kural 3 eşiklerin
config'den okunmasını ister, ama sayfa boyutu (limit) bir eşik değil, Binance'ın izin verdiği
sabit bir sayfalama parametresidir; bu yüzden sınıf sabiti olarak kalır. Canlı doğrulama (5
Ağustos 2026): `depth` yanıtında `symbol` alanı yoktur (`{"lastUpdateId","E","T","bids","asks"}`),
bu yüzden `_require_symbol` burada uygulanamaz — istek zaten yalnız `BTCUSDT` gönderir. Event
zamanı `E` (mesaj gönderim anı) alınır, `T` (transaction time) değil; ikisi birkaç ms farklı
olabilir ve Binance dokümantasyonu `E`'yi "bu defter durumunun gönderildiği an" olarak tanımlar.
Mevcut `"all"` üçlü paketi (mark/funding/OI) **değişmedi**; `order_book` yalnız açıkça
istendiğinde çekilir — geriye dönük testler kırılmadı.

### 4. `_collect()` üç bacağı da tek tick içinde toplar

`producer.py._collect()` artık şu sırayla çalışır: derivatives "all" → order_book →
(paylaşılan futures provider ile) spot "all". `core/context_producer.collect_derivatives`
zaten herhangi bir `BaseProvider` kabul ettiği için değişmeden yeniden kullanıldı — yeni bir
toplama yardımcı fonksiyonu yazmaya gerek kalmadı.

## Sonuçlar ve sınırlar

Canlı doğrulama (5 Ağustos 2026): `collect` komutu 12 satır yazdı (3 derivatives + 3 order_book
+ 6 spot); spot kapanmış 21:00-22:00 mumunu kullandı (22:0x'te çalıştırıldı), basis ≈%0.04,
spread ≈0.016 bps — makul büyüklükte, borsa saatinde.

Bilinçli olarak **hâlâ yok**:

- **Tarihsel backfill.** Spot OHLCV/basis/spread'in geçmişi toplanmıyor; yalnız canlı "anlık"
  toplama var (ADR-0004/Faz-1a paritesi). Funding/OI'nin ADR-0005'teki gibi bir geçmiş birikimi
  bu üç aile için henüz yapılmadı.
- **Yeni fragility feature'ı.** `signal_rules.yaml`'a basis veya spread için kural eklenmedi;
  bu metrikler `collection_coverage`/`get_health` raporunda henüz görünmez (ADR-0005 öncesi
  derivatives verisiyle aynı durum).
- **Yeni MCP aracı.** `get_market_snapshot` ve `get_premiums` SPEC'teki ayrı roadmap
  maddeleri olarak kalır; bu veri şimdilik yalnız PIT'te ve `collect` CLI çıktısındadır.
- **Scheduler değişmedi.** `ProducerScheduler`/`core/scheduler.py` mantığı aynı; yalnız
  `_collect()` içeriği genişledi.

Bu paket "spot/basis/spread verisi PIT'e akıyor ve canlı doğrulandı" demektir; "bu veriler
kararı etkiliyor" veya "kırılganlık/yön skoruna girdi" demek değildir.
