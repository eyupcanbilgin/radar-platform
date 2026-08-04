# ADR 0007 — Spot OHLCV, basis ve spread/depth collector'ları
Tarih: 4 Ağustos 2026
Durum: Kabul edildi
İlgili: ADR-0005, ADR-0006, SPEC.md §2.1–2.3

## Bağlam

ADR-0006 ile sürekli toplama ve işletim kanıtı tamamlandı. Faz 1 planında listelenen
iki veri ailesi hâlâ PIT deposuna girmiyordu:

- **Spot OHLCV:** Mevcut BinanceFuturesProvider yalnız USDT-M perp anlık değerlerini
  topluyor. Spot/perp basis hesabı için spot kapanış fiyatının PIT'te bağımsız kayıt
  olarak bulunması gerekiyor (SPEC §2.3: Coinbase Premium formülü ve §2.1: türev
  kapsama). radar-signal spot mumları freqtrade ile ayrıca çekiyor; bu provider oraya
  rakip değil, MCP bağlam zincirinin PIT kaydıdır.

- **Basis:** spot_price ve mark_price çiftinden hesaplanan `(spot − perp) / perp × 100`
  değeri SPEC §2.3'te "spot taker CVD Faz 2" notunun yanında yer alıyor; fakat basis
  anlık hesap olduğu için Faz 1'e alınabilir. Tarihsel basis serisi ise spot klines
  ile mark price history'nin eşleşmesiyle üretilir.

- **Spread/Depth:** SPEC §1.2 MVP kapsamında "spread ve sınırlı order-book depth"
  yer alıyor. Sınırlı = limit=20 ile anlık L2 snapshot; tam tape toplayıcı değil.

Bu üç ailenin eklenmesi ADR-0005 yeterli-geçmiş kapısı ve ADR-0006 scheduler
mimarisini değiştirmiyor; mevcut tick döngüsüne yeni provider'lar bağlanıyor.

## Kararlar

### 1. binance_spot_ohlcv.py — Kapalı saat mumu

Kaynak: `GET https://api.binance.com/api/v3/klines`
Parametreler: `symbol=BTCUSDT&interval=1h&limit=2` (sondan bir önceki = kapanmış)
Metrikler (ayrı RawObservation satırları):
  - `spot_open`, `spot_high`, `spot_low`, `spot_close` (USD, float)
  - `spot_volume` (BTC cinsinden klines'ın 5. sütunu)
  - `spot_taker_buy_volume` (BTC, sütun 9 — alıcı tarafı hacim asimetrisi için)

available_at semantiği: `close_time + 1 ms` — mum kapandıktan hemen sonra biliriz.
Bu ADR-0004'teki "saat kapanışından sonra çekilmiş anlık değeri geriye tarihleme yasak"
kuralıyla uyumludur: mum close_time'ı geçmiş bir an, biz onu close_time+1ms olarak
kaydediyoruz.

Provider adı: `binance_spot` — futures provider'dan ayrı izlenebilirlik.

Rate limit: `/api/v3/klines` 2 weight/istek; bütçe 1200 weight/dk. 5 dakikada bir
koşsak bile 2 weight/5dk = sorun yok.

### 2. binance_basis.py — Anlık ve tarihsel spot/perp basis

**Anlık basis:** spot `/api/v3/ticker/price` + perp `/fapi/v1/markPrice` çifti.
Her ikisi mevcut provider'larda zaten çekilip RawObservation'a yazılıyor; basis
provider bu iki değeri okuyup hesaplıyor — çift ağ isteği atmıyor, PIT'ten okuyup
türetiyor.

Tercih ettiğimiz tasarım: provider anlık olarak spot + mark price'ı aynı anda çekip
basis'i hesaplar. PIT'e üç ayrı satır yazar: `spot_price`, `mark_price`, `basis_pct`.
Böylece downstream feature'lar ham fiyatlara da ulaşabilir.

`basis_pct = (spot - mark) / mark * 100`

Negatif = contango (perp > spot, long pozisyon baskısı)
Pozitif = backwardation (spot > perp, nadiren)

**Tarihsel basis:** `/api/v3/klines` (spot 1h) × `/futures/data/indexPriceKlines`
(BTCUSDT perp 1h) çifti. available_at = `close_time + 1ms` (her iki mum için ortak).
Backfill BinanceFuturesHistoryProvider'ın sayfalama mantığını miras alır (ADR-0005
Karar 3); ileri sayfalama, limit ≤ 1000.

Provider adı: `binance_basis`

### 3. binance_depth.py — Anlık spread ve sınırlı depth

Kaynak: `GET https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=20`
Rate limit: 10 weight/istek (limit=20); 1200 bütçede 5 dk aralık = 2 weight/5dk nominal
+ nadir depth çekimi → bütçe içinde.

Metrikler (tek RawObservation, unit='composite'):
  - `bid_ask_spread_bps`: `(best_ask - best_bid) / mid * 10000` (baz puan)
  - `depth_bid_usd_1pct`: mid fiyatın %1 altındaki toplam alış USD hacmi
  - `depth_ask_usd_1pct`: mid fiyatın %1 üstündeki toplam satış USD hacmi

Tek composite kayıt yerine üç ayrı satır da yazılabilirdi; ancak bu üç metrik
atomik olarak aynı L2 snapshot'tan geldiği için birlikte anlam taşır ve aynı
available_at'e sahip olmaları zorunludur. Composite tasarım bu bütünlüğü korur.

available_at = retrieved_at (anlık snapshot, yayın gecikmesi bilinmiyor).

Provider adı: `binance_depth`

### 4. signal_rules.yaml — Yeni feature spec'ler

Yeni feature'lar ADR-0005 yeterli-geçmiş kapısı kuralını miras alır:

```yaml
basis_stress:
  min_samples: 48        # 2 gün × 24 saat
  min_span_days: 2
  max_gap_seconds: 7200  # 2 saatten uzun boşluk = feature_unavailable
  expected_period_seconds: 3600

spread_stress:
  min_samples: 12        # 12 saatlik anlık gözlem
  min_span_days: 0       # tek gün yeterli (anlık metrik)
  max_gap_seconds: 3600
  expected_period_seconds: 300   # 5 dk aralıkla toplanır
```

d=None: bu feature'ların hiçbiri şu an yönsel kural taşımıyor. ADR-0005 d=None
semantiği geçerli. Kırılganlık sinyali olarak r değerleri gelecek bir feature pakette
signal_rules.yaml'a eklenecek.

### 5. Scheduler entegrasyonu (ADR-0006 mimarisi korunur)

ProducerScheduler saat içi tick'ine yeni provider'lar eklenir:
- `BinanceSpotOhlcvProvider`: sadece kapanmış mum olduğu için saatlik publish'te çalışır
- `BinanceBasisProvider`: saat içi tick'te çalışır (anlık basis değerli; 5 dk aralık)
- `BinanceDepthProvider`: saat içi tick'te çalışır (5 dk aralık)

Hata döngüyü durdurmaz (ADR-0006 Karar 2). Her provider bağımsız try/except bloğunda;
biri başarısız olursa diğerleri koşmaya devam eder.

### 6. Observation model genişlemesi

`btc_radar/models/observation.py` içindeki metrik Literal'ı yeni metrik adlarını
kapsamalı. Alternatif: Literal yerine `str` — SPEC §3.3 şema değişikliğinde test
kırılsın istiyor, bu yüzden Literal korunur ve genişletilir.

### 7. Fixture'lar kaydedilmiş gerçek yanıtlar

Her yeni provider için `tests/fixtures/` altına gerçek Binance endpoint'inden
alınan anonim yanıt kaydedilir. CI canlı ağa çıkmaz.

`binance_spot_klines_btcusdt_1h.json`
`binance_spot_ticker_btcusdt.json`
`binance_futures_index_klines_btcusdt_1h.json`
`binance_depth_btcusdt_limit20.json`

## Sonuçlar ve sınırlar

Bu paket PIT'e üç yeni veri ailesi ekler ve Faz 1 planının "spot/perp basis,
spread/depth collector'larını ekle" maddesini kapatır.

Bilinçli olarak hâlâ yok:
- Basis ve spread feature'ları için kırılganlık kuralları (r değerleri). Kapsam:
  veri toplanıyor, yeterli-geçmiş kapısı blocker yazıyor, d=None.
- Spot CVD (taker hacim imbalance'ı): spot_taker_buy_volume topluyoruz ama
  rolling CVD feature'ı ayrı bir iş paketidir.
- Depth tarihsel backfill: L2 snapshot'ın tarihsel verisi Binance'ta yok; yalnız
  anlık toplanır.
- Kesinti bildirimi / Telegram alarm: ADR-0006'da Faz 3 olarak işaretli, bu paketle
  değişmiyor.

Bu paket "spot/perp basis ve spread/depth verisi PIT'te" demektir; "bu verilerden
kırılganlık skoru üretiliyor" demek değildir.
