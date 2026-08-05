# RADAR Hedefe Geliştirme Planı

**Durum:** AKTİF
**Başlangıç:** 4 Ağustos 2026
**Ürün sahibi:** Eyüpcan
**Tek aktif depo:** `radar-platform`
**İlk çalışma dalı:** `feature/eleme-tezgahi`

## 1. Kuzey Yıldızı

RADAR'ın hedef ürünü şudur:

> Çok kaynaklı piyasa verisini otomatik izleyen; yalnız ölçülmüş bir kurulum oluştuğunda
> açıklanabilir kırılganlık, volatilite genişlemesi riski, veri güveni ve blocker uyarısı
> üreten; yön ölçülmedikçe `direction=null`/`WAIT` kalan ve uyarılarının ileri sonuçlarını
> değişmez bir defterde ölçen kişisel piyasa risk karar-destek sistemi.

Kârlılık bir yazılım özelliği veya vaat değildir. Ürün v1'in kanıt koşulu, kırılganlık
uyarılarının kilitli değerlendirme ve forward paper döneminde kalibre olmasıdır. Sistem
gerçek emir göndermez ve çıktılar `DENEYSEL/PAPER` etiketi taşır.

## 2. Bugünkü Gerçeklik

| Alan | Bugünkü durum | Hedefe etkisi |
|---|---|---|
| Araştırma altyapısı | Manifest, Registry, maliyet modeli, replay ve test temeli var | Korunacak |
| Yönsel avantaj | S-0003 ve S-0004 Development'ta reddedildi; eski seans ailesi yönsel öngörü göstermedi | Ürün v1 için park edildi; ADR-0004 yeniden-açma kapısı geçilmeden yeni yön denemesi yok |
| Eleme raporu | 126 kayıt var; istatistik uygulamasında doğruluk kusurları bulundu | Sonuçlar geçici; yeniden analiz edilecek |
| MCP | Binance mark/funding/OI provider'ı, PIT collector, fail-closed context publisher; ayrıca tarihsel funding/OI backfill'i ve iki kırılganlık feature'ı (ADR-0005); spot OHLCV, spot/perp basis ve order-book spread/depth toplayıcıları (ADR-0007) | Kırılganlık gözlemi çalışıyor; yön ve rejim hâlâ kapalı |
| Signal ürünü | BTC 1h runtime exact-hour context'i tüketiyor ve değişmez WAIT yazıyor; karar sonuçları ölçülüyor (ADR-0010), teslimat idempotent outbox üzerinden bağlı (ADR-0011) | Kırılganlık uyarı kartı ve ileri olay kalibrasyonu Faz 2'de tamamlanacak |
| Veri kapsamı | Signal BTC futures OHLCV; MCP anlık mark/funding/OI + 120 gün settled funding, ~30 gün saatlik OI + canlı spot OHLCV/basis/spread; spot OHLCV backfill ve yeni ailelerin coverage kanıtı (ADR-0008) | Basis/depth yalnız canlı birikir; kesintiler `live_only` olarak görünür |
| Operasyonel güven | MCP scheduler/heartbeat/kapsama kanıtı var; Signal ledger-outbox crash boşluğu sınırlı reconciliation ile kapalı; expiry, Telegram env, kesinti bildirimi ve risk kapıları eksik | Paper karantina öncesi kapatılacak |

## 3. Değişmez Ürün İlkeleri

1. Gerçek borsa emri yoktur; execution ayrı ve gelecekteki bir karar kapısıdır.
2. LLM canlı yön, boyut veya emir kararı vermez.
3. `WAIT/NO-TRADE` birinci sınıf ve ölçülen bir çıktıdır.
4. Her karar `as_of`, `snapshot_id`, veri sürümü, kural sürümü ve gerekçeyle replay edilebilir.
5. Yönsel setup, rejim ve risk ayrı katmanlardır; rejim tek başına yön sinyali sayılmaz.
6. Yeni veri kaynağı yalnız point-in-time zincirine bağlanırsa ve marjinal katkısı ölçülürse eklenir.
7. Başarı; win-rate, kaynak sayısı veya test sayısıyla değil maliyet sonrası beklenti, drawdown,
   kalibrasyon ve forward sapmayla ölçülür.
8. Locked OOS bir kez açılır; geliştirme sonucu hiçbir zaman final OOS diye sunulmaz.
9. Ürün v1 yön tahmini yapmaz; `direction=null` ölçülmemiş yönün tek doğru gösterimidir.

## 4. Hedef Mimari

```text
Collectors
  -> append-only RawObservation / PIT store
  -> versioned FeatureSnapshot
  -> fragility + volatility-risk features
  -> data confidence + blockers
  -> deterministic Alert Gate
  -> FRAGILITY / DATA-UNAVAILABLE / NORMAL observation + WAIT DecisionCard
  -> Telegram + decision ledger
  -> outcome evaluator (MFE, MAE, +1h, +4h, +24h, costs)
```

MCP bu akışın zaman-kritik taşıyıcısı değildir. Snapshot deposunu AI ve insan incelemesine
salt-okunur sunar. Signal servisi sürümlü contract üzerinden snapshot/API tüketir; MCP veya
LLM kesintisi karar döngüsünü kilitlemez.

## 5. Uygulama Fazları

### Faz 0 — Kanıtı ve kaynak gerçeğini onar

**Amaç:** Üzerine ürün kurulacak araştırma kapısını güvenilir hâle getirmek.

- [x] `signal_pulse` için ufukla eşleşen null dağılımı kullan.
- [x] Örtüşen getirileri blok/olay örneklemesiyle ele al; efektif olay sayısını raporla.
- [x] Test yönünü önceden tanımla; sonuç işaretine göre kuyruk seçme davranışını kaldır.
- [x] `n=0/NaN` testleri geçersiz say ve FDR evreninde yalnız geçerli p-değerleri kullan.
- [x] Funding, hafta sonu ve yüksek-vol rejimlerinde ardışık mumları bağımsız olay sayma.
- [x] Seansları DST-aware tanımla ve karar fiyatını sonraki mum açılışına taşı.
- [x] S-0002b ATR stop/funding koşularını append-only `INVALID` kaydına al.
- [x] Eleme raporunu `GEÇİCİ/GERİ ÇEKİLDİ` olarak işaretle.
- [ ] İncelenen signal commit'ine bağlı bağımsız onay kaydı ve temiz repo sonrası denetlenmiş
  Development reanalysis üret.
- [x] Her araştırma çıktısına code SHA, dataset manifest/hash, yöntem sürümü ve artefakt hash'i bağla.
- [x] Signal lint, test ve format kapılarını temizle.

**Kabul kapısı:** Denetlenmiş istatistik testleri yeşil, lint temiz, geçersiz/eski sonuçlar
final diye görünmüyor ve yeni koşu temiz commit + doğrulanmış manifest olmadan `accepted`
alamıyor.

### Faz 1 — BTC 1h paper dikey dilim

**Amaç:** Platform genişletmeden çalışan ürün döngüsünü görmek.

- [x] İlk teknik sözleşme kapsamını `BTCUSDT · 1h · LONG/SHORT/WAIT · paper` olarak sabitle;
  aktif ürün v1 profilini ADR-0004 ile `direction=null`/`WAIT` kırılganlık uyarısına daralt.
- [x] İlk Binance public mark/funding/OI collector'ını ve PIT yazımını ekle.
- [x] Binance spot OHLCV, basis ve spread/depth collector'larını ekle (MCP ADR-0007).
- [x] Tarihsel settled funding ve saatlik OI'yi PIT'e biriktir; yeterli-geçmiş şartını tanımla
  ve yalnız kırılganlık feature'larını kur (ADR-0005). Yön ve rejim kapalı kalır.
- [x] OI collector'ını process supervision ile sürekli çalıştır; geçmiş endpoint'i sınırlıdır.
  - [x] `collect` her koşuda en yeni geçmiş sayfasını da yazıyor; `backfill` sayfalı ve bütçeli.
  - [x] Scheduler, heartbeat ve kesintisiz işletim kanıtı (ADR-0006): iki ritimli tick,
    append-only koşu kütüğü, veriden türeyen kapsama raporu, tek örnek kilidi.
  - [ ] Kesinti bildirimi (alarm/Telegram operasyon kanalı) — Faz 3.
- [x] `contracts/decision-context/v1` sözleşmesini oluştur ve iki serviste ortak fixture ile
  doğrula.
- [x] Kapanmış 1h mum için PIT güvenli, versioned `FeatureSnapshot` üret.
- [x] Her saat karar üret; setup yoksa açık gerekçeli `WAIT` kartı yaz.
  - [x] Deterministik karar motoru, context-missing WAIT ve append-only ledger.
  - [x] Public Binance kapalı mum adaptörü, exact-hour context inbox consumer'ı ve UTC
    tek-sefer/daemon scheduler kodu.
  - [x] Gerçek Binance -> PIT -> unscored snapshot -> exact-hour MCP context producer.
  - [x] Producer scheduler, process supervision/heartbeat ve kesintisiz işletim kanıtı
    (ADR-0006). Kalan operasyon işi kesinti bildirimi ve uzak izlemedir.
- [ ] Signal candidate -> policy -> ledger -> outbox -> Telegram hattını gerçek dry-run sürecine bağla.
  - [x] Mevcut yönsüz `DecisionCardV1` -> deterministik mesaj -> idempotent outbox -> mevcut
    Telegram/console pump hattını bağla; sınırlı crash-gap reconciliation ekle (Signal ADR-0011).
  - [ ] Kabul edilmiş setup ailesini aynı hatta bağla; yön yalnız Faz 2 araştırma kapısından gelir.
- [x] Kararların +1h/+4h/+24h sonuçlarını, MFE/MAE ve veri sağlığını otomatik kaydet
  (Signal ADR-0010). Append-only `decision_outcomes` defteri; maliyet `config/costs.yaml`'dan
  gelir, ufuk kapanmadan sonuç `pending` kalır, WAIT kararları `opportunity_return` ile ölçülür.

**İlk çekirdek veri aileleri:**

1. Spot ve perpetual fiyat/hacim
2. Funding
3. Open interest
4. Spot-perpetual basis
5. Spread ve sınırlı order-book depth
6. FOMC/CPI gibi sürümlü olay takvimi

On-chain, haber, opsiyon, ETF akışı, sosyal duygu ve 91 bağlantılık kaynak havuzu bu fazın
dışındadır. Her biri daha sonra ayrı ablation ile katkı gösterirse eklenir.

**Kabul kapısı:** Kesintisiz çalışan `veri -> snapshot -> karar -> Telegram -> sonuç` zinciri;
aynı snapshot'ın 100 replay'inde bit-bit aynı karar; veri eksik/bayatken yönsel karar yok.

### Faz 2 — Kırılganlık uyarısı kalibrasyonu ve araştırma arşivi

**Amaç:** Yön iddia etmeden, kırılganlık uyarısının ileri oynaklık ve olumsuz hareket
riskiyle ilişkisini sızıntısız ölçmek; reddedilmiş yönsel araştırmayı değiştirmeden korumak.

- [x] BTC 1h için basit, açıklanabilir yönsel aileleri hipotez kartlarıyla ön-kayıt et
  (S-0003 ve S-0004 ölçüldü; ikisi de Development düzeyinde reddedildi).
- [x] Yönsel ürün araştırmasını park et; yeniden-açma kapısını tanımla (Platform ADR-0004).
- [ ] Her aileyi önce ham nabız, sonra purged walk-forward + embargo ile değerlendir.
  - [x] Protokol ve CLI hazır (Signal ADR-0014): deterministik fold planı, label horizon'a
    göre purge, train-test arası ≥1 gün embargo, locked OOS varsayılan olarak kapalı.
  - [x] İki gerçek yönsel aileyi protokolle koş ve sonucu hipotez kartına bağla
    (S-0003/ADR-0017, S-0004/ADR-0018; ikisi de reddedildi).
- [x] Net getiriyi `realistic` ve `taker_heavy` maliyet senaryolarında ölç.
- [ ] DSR'a ek olarak PBO/CSCV veya White Reality Check uygula.
  - [x] Registry-güdümlü DSR + PBO/CSCV altyapısı ve sentetik kabul testleri (ADR-0019).
  - [ ] Sonraki ön-kayıtlı hipotezin Development raporuna iki kapıyı da uygula.
- [ ] ±%20 parametre hassasiyeti ve dönem/venue kırılganlığını raporla.
  - [x] Config-güdümlü ±%20 parametre hassasiyet kapısı hazır (ADR-0019).
  - [x] Göreli dönem/venue kırılganlık kapısı ve sentetik kabul testleri hazır (ADR-0020).
  - [ ] Sonraki hipotezde hassasiyet ile gerçek dönem/venue kırılganlık raporunu üret.
- [x] Baseline'lar: cash, buy-and-hold ve basit trend kontrolü (ADR-0016).
- [ ] Bir veri ailesini eklemeden/çıkarmadan önce aynı koşuda ablation yap.
  - [x] Eşleşmiş fold ve iki maliyet senaryolu ablation kapısı hazır (ADR-0019).
  - [ ] Sonraki çok-aileli hipotezde ön-kayıtlı ablation raporunu üret.
- [ ] BTC'de kabul edilen sabit kuralları ETH'de bağımsız replikasyon adayı olarak sınama.

**Aktif kırılganlık işleri:**

- [x] F-0001 ileri olay etiketini ön-kayıt et: gerçekleşen volatilite genişlemesi ve maksimum
  mutlak sapma; yön etiketi yok (`config/fragility_calibration.yaml`).
- [ ] Funding stress ve OI buildup için purged walk-forward kalibrasyon raporu üret.
  - [x] Train-only olasılık ve pooled out-of-fold metrik çekirdeği hazır (Signal ADR-0021).
  - [x] PIT kırılganlık + OHLCV'den provenance bağlı tetik/etiket üreticisi hazır (ADR-0022).
  - [x] Anahtarsız Coinbase spot 1h indiricisi ve çok-venue manifest altyapısı hazır
    (Signal ADR-0023; ham veri git dışı).
  - [x] Manifest + ana/iki ablation context + iki venue girdisini fail-closed bağlayan kanıt
    koşusu orkestratörü hazır (Signal ADR-0024; gerçek ölçüm yapılmadı).
  - [ ] Manifest doğrulanmış gerçek iki-venue girdisiyle F-0001 ölçümünü koş.
- [ ] Precision/recall, calibration, lead time, false-alarm ve abstention metriklerini raporla.
- [ ] Eksik/yetersiz sonucu `unavailable` tut; sakin veya nötr olay olarak sayma.
- [ ] Basis, spread/depth ailelerini yeterli canlı geçmişten sonra ayrı ablation ile değerlendir.
- [ ] Saatlik uyarı kartını direction üretmeden ledger/outbox hattına bağla.

**Kabul kapısı:** Development ve validation'da veri kapsamı yeterli; kalibrasyon ve
precision/recall config kapılarını geçen; tek döneme yoğunlaşmayan; baseline uyarı oranını
aşan kırılganlık modeli. Bu kapı yön veya kârlılık kanıtı değildir.

### Faz 3 — Forward paper karantina ve ürün güvenliği

**Amaç:** Tarihsel kırılganlık kalibrasyonu ile gerçek zamanlı uyarı davranışı arasındaki
sapmayı ölçmek.

- [ ] Minimum 4 hafta AND 100 bağımsız karar/sinyal AND 2 rejim koşulunu uygula.
- [ ] Tercih edilen gözlem süresi 8-12 haftadır; fırsat koşulu dolmadan süre tek başına yetmez.
- [x] Telegram `.env` yükleme ve console fallback davranışını fail-closed yap
  (Signal ADR-0013; açık `telegram|console` modu).
- [x] Ledger/outbox crash boşluğunu gider veya onarım/reconciliation worker'ı ekle
  (Signal ADR-0011; saatlik DecisionCard hattı).
- [ ] `valid_until`, `max_entry_deviation` ve aktif expiry'yi teslimden önce uygula.
- [ ] Webhook kimlik doğrulama/replay koruması ekle.
  - [x] Enricher ingress için HMAC, timestamp ve kalıcı atomik nonce kapısı (Signal ADR-0015).
  - [ ] Freqtrade çıkışına dinamik HMAC üreten yerel signer adaptörünü bağla; imzasız fallback yok.
- [ ] Stop mesafeli risk bütçesi, toplam açık risk ve BTC/ETH korelasyon limiti ekle.
- [ ] Günlük/haftalık zarar, maksimum drawdown, stale-data ve manuel pause kill-switch'lerini ekle.
- [ ] Paper-sim fill/slippage/latency drift raporu üret.

**Kabul kapısı:** Maliyet sonrası forward beklenti pozitif, drawdown bütçe içinde, teslimat ve
reconciliation hatası yok, bütün kill-switch senaryoları testli. Aksi durumda gerçek para yok.

### Faz 4 — Kapsam genişletme

Faz 3 geçilmeden başlamaz.

Öncelik sırası: ETH replikasyonu -> cross-venue türev -> opsiyon rejimi -> stablecoin riski ->
kurumsal akış/makro -> on-chain -> yapılandırılmış haber. Her kaynak ailesi `çıplak` ve
`+kaynak` OOS kıyasında ölçülür; katkı göstermiyorsa üretim kapsamına alınmaz.

## 6. Başarı Göstergeleri

| Grup | Ölçüt |
|---|---|
| Ekonomik | Maliyet sonrası expectancy, net PnL, profit factor, drawdown, Calmar |
| İstatistik | Efektif bağımsız örneklem, DSR/PBO, zaman/varlık replikasyonu |
| Uyarı kalitesi | Precision/recall, lead time, false-alarm, abstention, calibration/Brier |
| Operasyon | Veri yaşı, null oranı, provider drift, pending/dead outbox, replay uyumu |
| Gerçekçilik | Sim-paper fill, spread, slippage ve latency sapması |

Win-rate tek başına kabul ölçütü değildir.

## 7. Şimdilik Yapılmayacaklar

- Gerçek emir veya trade yetkili API anahtarı
- Bütün kaynak linklerini collector'a çevirmek
- LLM'e yön/pozisyon/emir yetkisi vermek
- Alpha kanıtlanmadan dashboard, mobil uygulama veya kapsamlı ML platformu kurmak
- Geliştirme verisindeki en iyi sonucu “final” diye seçmek
- Kabul edilmiş setup olmadan rejim skorunu doğrudan pozisyona çevirmek

## 8. Aktif çalışma paketleri

`WP-0001 — Araştırma Kapısı Onarımı`

1. Eleme istatistiğinin denetlenmiş v2 uygulaması
2. Eski raporun kanıt durumunun düzeltilmesi
3. S-0002b geçerlilik düzeltmesi
4. Registry/artefakt provenance genişletme tasarımı
5. Signal lint ve test kapılarının yeşile alınması

**İlerleme:** Kodlama ve yerel doğrulama tamamlandı; append-only verdict event kütüğü ve
temiz-repo/manifest/locked-OOS/commit'e bağlı bağımsız onay korumalı reanalysis koşucusu
eklendi. Kalan kapı bu commit'in bağımsız incelenmesi, onay kaydının ayrı commit'lenmesi ve
Development reanalysis koşusudur.

WP-0001'in bağımsız araştırma onay kapısı yeni yönsel strateji kabulünden önce hâlâ
geçerlidir. Aşağıdaki WP-0002 tek onaylı BTC veri taşıma dilimidir; yeni alpha/strateji veya
geniş provider ailesi iddiası değildir.

### WP-0002 — İlk gerçek veri ve context taşıması

**Durum:** Kodlama, test ve canlı smoke tamamlandı.

1. Binance USD-M public mark/funding/OI provider ve `get_derivatives`
2. A→B→A revizyonunu ve farklı bilgi-zamanlarını koruyan append-only PIT
3. Snapshot ID/hash/cutoff okuma-yazma bütünlük doğrulaması
4. Unscored/fail-closed exact-hour context producer
5. Atomik no-overwrite publisher ve iki-servis consumer smoke

Bu paket yön/rejim skoru açmaz. Bir sonraki ürün işi historical OI/funding serisini PIT'e
toplamak, yeterli geçmiş şartını tanımlamak ve yalnız kanıtlı **fragility** feature'larını
kurmaktır. Direction, kabul edilmiş signal setup'ı olmadan null kalır.

### WP-0003 — Tarihsel türev geçmişi ve kırılganlık kapısı

**Durum:** Kodlama, test ve canlı smoke tamamlandı (MCP ADR-0005).

1. `binance_futures_history` provider: settled funding (ileri sayfalama) ve saatlik OI
   (geriye sayfalama; ~30 gün saklama sınırı adlandırılmış hataya çevrildi)
2. Backfill satırlarında yayın-anı semantiği: `available_at = event_time + publication_lag`,
   canlı gözlemden ayrı provider adıyla; backfill kesintisiz işletim kanıtı sayılmaz
3. PIT deposunda revizyon-farkında, look-ahead'siz `read_series`
4. Yeterli-geçmiş kapısı: `min_samples`, `min_span_days`, `max_gap_seconds`; ihlal
   `feature_unavailable:<feature>:<neden>` blocker'ı üretir
5. `funding_stress` ve `oi_buildup` kırılganlık feature'ları; midrank yüzdelik; `d=None`
6. Feature kanıtı değişmez snapshot'a bağlandı; girdi digest'i kullanılan geçmişi kapsıyor

Canlı doğrulama: 360 settlement + 744 saatlik OI kovası toplandı; `2026-08-04T14:00Z`
context'i `fragility=0.0`, `direction=null`, blocker `direction_rules_unavailable` ile
yayınlandı. Yetersiz geçmişli bir saat için kapı blocker yazarak kapandı.

Bu paket kârlılık veya güvenilir yön sinyali iddiası **değildir**.

### WP-0004 — Sürekli toplama ve işletim kanıtı

**Durum:** Kodlama, test ve canlı daemon smoke tamamlandı (MCP ADR-0006).

1. İki ritimli `ProducerScheduler`: saat içi toplama, kapanan saat için tek yayın
2. Hata döngüyü durdurmaz; tick içinde retry yok, aralık son **denemeden** ölçülür
3. Append-only heartbeat kütüğü: sürecin koştuğunun kanıtı, hata kaydı silinmez
4. Veriden türeyen kapsama raporu: serinin tam olduğunun kanıtı; eşikler feature config'inden
5. Sınırlı ve `catch_up` etiketli yakalama; pencere aşımı `skipped` olarak raporlanır
6. Tek örnek kilidi (otomatik bayat temizlik yok) ve birinci sınıf tek-tick modu
7. `status` komutu + `get_health` içinde toplama sağlığı

Canlı doğrulama: daemon 15 sn aralıkla üç toplama yaptı, aynı saati ikinci kez yayınlamadı;
`status` 7 günlük pencerede iki metrik için de `coverage_ratio=1.0` ve `hours_behind=0`
raporladı; sert öldürülen süreçten kalan kilit ikinci başlatmayı reddetti.

### WP-0005 — Spot OHLCV, spot/perp basis ve order-book spread/depth toplama

**Durum:** Kodlama, test ve canlı `collect` smoke tamamlandı (MCP ADR-0007).

1. `BinanceSpotProvider`: saatlik spot OHLCV (yalnız kapanmış mum; açık mum fail-loud atılır)
2. Spot/perp basis: `(Binance spot − Binance perp mark) / mark × 100`, Binance içi hesap
   (cross-exchange bağımsız değil, `funding_stress`/`oi_buildup` ile aynı kırılganlık ailesi)
3. `BinanceFuturesProvider`'a `order_book` metriği: USD-M perp defterinden spread (bps) ve
   sabit `limit=20` sayfalık iki taraflı notional depth
4. `_collect()` üç bacağı da tek tick içinde toplar; futures provider basis bacağıyla
   paylaşılır (ikinci bir `premiumIndex` isteği açılmaz)

Canlı doğrulama (5 Ağustos 2026): `collect` 12 satır yazdı (3 derivatives + 3 order_book + 6
spot); açık (henüz kapanmamış) mum kullanılmadı; basis ≈%0.04, spread ≈0.016 bps.

Bu paket tarihsel backfill, yeni fragility feature'ı veya yeni MCP aracı açmaz; `direction`
hâlâ null. Tarihsel spot ve coverage işi WP-0006'da tamamlanmıştır.

### WP-0006 — Spot OHLCV geçmişi ve yeni collector coverage kanıtı

**Durum:** Kodlama, test ve canlı sınırlı smoke tamamlandı (MCP ADR-0008).

1. Ayrı `binance_spot_history` provider ile kapanmış spot 1h mumları ileri sayfalama
2. Backfill availability: `closeTime + publication_lag`; gerçek ingest zamanı ayrı korunur
3. `backfill --spot-days` ile sınırlı, bütçeli ve idempotent PIT yazımı
4. Spot close, spot/perp basis ve order-book spread için scoring'den ayrı coverage config'i
5. Basis/depth tarihsel uçları olmadığı için `history_mode=live_only`; sahte geçmiş yok

Canlı doğrulama (5 Ağustos 2026): 1 günlük spot penceresi 23 kapanmış mumdan 115 OHLCV
gözlemi yazdı; en büyük boşluk 3600 saniye, availability kapanış + 60 saniyeydi.

Bu paket yeni feature, fragility veya direction kuralı açmaz. `direction` her koşulda null
kalır; coverage sağlığı yönsel karar izni değildir.
