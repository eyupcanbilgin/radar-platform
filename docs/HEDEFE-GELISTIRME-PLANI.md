# RADAR Hedefe Geliştirme Planı

**Durum:** AKTİF
**Başlangıç:** 4 Ağustos 2026
**Ürün sahibi:** Eyüpcan
**Tek aktif depo:** `radar-platform`
**İlk çalışma dalı:** `feature/eleme-tezgahi`

## 1. Kuzey Yıldızı

RADAR'ın hedef ürünü şudur:

> Çok kaynaklı piyasa verisini otomatik izleyen; yalnız ölçülmüş bir kurulum oluştuğunda
> açıklanabilir BTC/ETH `LONG`, `SHORT` veya `WAIT` kararı üreten, riski sınırlayan ve
> kararlarının maliyet sonrası sonuçlarını değişmez bir defterde ölçen kişisel trading
> karar-destek sistemi.

Kârlılık bir yazılım özelliği veya vaat değildir. Kilitli OOS ve forward paper ölçümünde
kanıtlanması gereken kabul koşuludur. Kanıt oluşana kadar sistem gerçek emir göndermez ve
çıktılar `DENEYSEL/PAPER` etiketi taşır.

## 2. Bugünkü Gerçeklik

| Alan | Bugünkü durum | Hedefe etkisi |
|---|---|---|
| Araştırma altyapısı | Manifest, Registry, maliyet modeli, replay ve test temeli var | Korunacak |
| Yönsel avantaj | Kabul edilmiş strateji yok | Yeni stratejiden önce güvenilir nabız kapısı gerekir |
| Eleme raporu | 126 kayıt var; istatistik uygulamasında doğruluk kusurları bulundu | Sonuçlar geçici; yeniden analiz edilecek |
| MCP | Faz 0 iskeleti; yalnız `get_health`, gerçek provider yok | Önce dar veri zinciri tamamlanacak |
| Signal ürünü | Backtest ve bildirim parçaları var, birbirine bağlı değil | Tek dikey paper akışı kurulacak |
| Veri kapsamı | BTC/ETH futures OHLCV, funding ve FOMC ağırlıklı | OI, spot/perp basis ve veri sağlığı öncelikli |
| Operasyonel güven | Expiry, outbox atomikliği, Telegram env ve risk kapıları eksik | Paper karantina öncesi kapatılacak |

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

## 4. Hedef Mimari

```text
Collectors
  -> append-only RawObservation / PIT store
  -> versioned FeatureSnapshot
  -> directional Setup Engine
  -> regime + fragility observation
  -> deterministic Risk Gate
  -> LONG / SHORT / WAIT DecisionCard
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

- [ ] İlk ürün kapsamını `BTCUSDT · 1h · LONG/SHORT/WAIT · paper` olarak sabitle.
- [ ] Binance spot/futures OHLCV, funding, OI, basis ve spread/depth collector'larını ekle.
- [ ] OI verisini append-only PIT olarak hemen toplamaya başla; geçmiş endpoint'i sınırlıdır.
- [ ] `contracts/decision-context/v1` sözleşmesini oluştur.
- [ ] Kapanmış 1h mum için versioned `FeatureSnapshot` üret.
- [ ] Her saat karar üret; setup yoksa açık gerekçeli `WAIT` kartı yaz.
- [ ] Signal candidate -> policy -> ledger -> outbox -> Telegram hattını gerçek dry-run sürecine bağla.
- [ ] Kararların +1h/+4h/+24h sonuçlarını, MFE/MAE ve veri sağlığını otomatik kaydet.

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

### Faz 2 — Yönsel araştırma ve kabul kapısı

**Amaç:** Basit baseline'ları aşan maliyet sonrası avantaj aramak; kazanan uydurmamak.

- [ ] BTC 1h için basit, açıklanabilir yönsel aileleri hipotez kartlarıyla ön-kayıt et.
- [ ] Her aileyi önce ham nabız, sonra purged walk-forward + embargo ile değerlendir.
- [ ] Net getiriyi hesap özel maker/taker, funding, spread, kayma ve latency ile ölç.
- [ ] DSR'a ek olarak PBO/CSCV veya White Reality Check uygula.
- [ ] ±%20 parametre hassasiyeti ve dönem/venue kırılganlığını raporla.
- [ ] Baseline'lar: cash, buy-and-hold ve basit trend kontrolü.
- [ ] Bir veri ailesini eklemeden/çıkarmadan önce aynı koşuda ablation yap.
- [ ] BTC'de kabul edilen sabit kuralları ETH'de bağımsız replikasyon adayı olarak sınama.

**Kabul kapısı:** Development ve validation'da gerçekçi + taker-heavy maliyette pozitif;
tek döneme yoğunlaşmayan; baseline'ı aşan; parametre hassasiyetinde çökmeyen aday. Bu kapı
locked OOS başarısı değildir, yalnız forward karantina adaylığıdır.

### Faz 3 — Forward paper karantina ve ürün güvenliği

**Amaç:** Backtest ile gerçek zamanlı karar üretimi arasındaki sapmayı ölçmek.

- [ ] Minimum 4 hafta AND 100 bağımsız karar/sinyal AND 2 rejim koşulunu uygula.
- [ ] Tercih edilen gözlem süresi 8-12 haftadır; fırsat koşulu dolmadan süre tek başına yetmez.
- [ ] Telegram `.env` yükleme ve console fallback davranışını fail-closed yap.
- [ ] Ledger/outbox crash boşluğunu gider veya onarım/reconciliation worker'ı ekle.
- [ ] `valid_until`, `max_entry_deviation` ve aktif expiry'yi teslimden önce uygula.
- [ ] Webhook kimlik doğrulama/replay koruması ekle.
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
| Karar kalitesi | LONG/SHORT/WAIT kapsamı, abstention oranı, calibration/Brier |
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

## 8. İlk Aktif Çalışma Paketi

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

Bu paket bitmeden yeni strateji veya provider eklenmez.
