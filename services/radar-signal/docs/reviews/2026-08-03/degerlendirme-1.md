<!-- Kaynak: Harici AI değerlendirmesi #1 (kapsamlı rapor) · Alınma: 3 Ağustos 2026 · CR-002'nin kanıt kaynağı -->

Eyüpcan, yüklediğin **RADAR Sistemi v1.0** dokümanını mimari, istatistiksel güvenilirlik, canlı-backtest tutarlılığı, ürün değeri ve operasyonel risk açısından değerlendirdim.

# Genel hüküm

Bu proje sıradan bir "indikatörleri birleştirip Telegram'a sinyal atan bot" tasarımından belirgin biçimde daha olgun. Özellikle şu kararların çok doğru:

* LLM'in canlı sinyal döngüsünden çıkarılması
* Emir göndermeyen karar-destek ürünü olarak sınırlandırılması
* Her stratejinin hipotez kartından başlaması
* Reddedilen stratejilerin de kaydedilmesi
* Maliyet, slippage, funding ve walk-forward testlerinin baştan düşünülmesi
* Rejim verilerinin doğrudan yön sinyali değil filtre olarak ele alınması
* Sistem defteri ile kullanıcının gerçek işlem defterinin ayrılması

Ancak şu anda sistemin önündeki temel risk "stratejilerin iyi olup olmaması" değil. Asıl risk, **çok iyi görünen araştırma metodolojisinin veri zamanlaması, deney seçimi ve execution simülasyonu yüzünden gerçekte olduğundan daha güvenilir sonuç üretmesi**.

Benim değerlendirmem:

| Alan                        | Durum                                                                   |
| --------------------------- | ----------------------------------------------------------------------- |
| Ürün fikri                  | Çok güçlü                                                               |
| Temel felsefe               | Çok güçlü                                                               |
| Araştırma disiplini         | Güçlü, fakat bazı önemli açıklar var                                    |
| Servis mimarisi             | Mantıklı, snapshot ve dayanıklılık eksik                                |
| Rejim skorlaması            | İyi başlangıç, fakat doğrusal formül fazla kırılgan                     |
| Backtest–canlı tutarlılığı  | Şu an en kritik teknik zayıflıklardan biri                              |
| Operasyonel güvenilirlik    | Henüz tasarımın gerisinde                                               |
| Gerçek sinyal güvenilirliği | Backtest tamamlanmadığı için kanıtlanmamış                              |
| Mevcut aşama                | Sağlam araştırma prototipi; henüz karar-kalitesi kanıtlanmış ürün değil |

---

# 1. Mimari değerlendirme

## 1.1 İki proje ayrımı doğru

`btc-radar` ile `radar-signal` ayrımı mantıklı:

* `btc-radar`: veri toplama, normalizasyon, kalite, özellik ve rejim üretimi
* `radar-signal`: strateji, sinyal yaşam döngüsü, dry-run ve bildirim
* Entegrasyon: HTTP

Bu ayrım sayesinde rejim motoru strateji motorundan bağımsız test edilebilir. Ayrıca gelecekte aynı rejim servisini dashboard, araştırma notebook'u veya başka strateji motorları da tüketebilir.

Fakat bu ayrım yeni bir problem oluşturuyor: **aynı mum için hangi rejim snapshot'ının kullanıldığı kesin olarak belirlenmezse determinizm bozulur.**

### Kritik sorun: "latest" veri determinizmi bozar

Şu akışı düşün:

1. BTC 15 dakikalık mum 20:15'te kapanır.
2. `radar-signal`, 20:15:02'de `btc-radar` servisini çağırır.
3. Funding kaynağı 20:15:04'te güncellenir.
4. Backtest veya replay sırasında aynı mum için sorgu tekrar çalıştırılır.
5. Bu kez yeni funding değeri kullanılır.

Aynı mum ve aynı kod olmasına rağmen farklı rejim sonucu çıkar.

Bu durum doğrudan şu ilkeyle çelişir:

> Aynı veri her zaman aynı sinyali üretir.

Sorun kodun nondeterministik olması değil; **kullanılan veri snapshot'ının tanımlanmamış olmasıdır.**

### Öneri: immutable regime snapshot

Sinyal motoru "güncel rejimi" değil, şu tür bir snapshot istemeli:

```text
GET /v1/regime/snapshot
    ?asset=BTC
    &as_of=2026-08-03T17:15:00Z
```

Cevap en az şu alanları taşımalı:

```json
{
  "snapshot_id": "rgs_20260803_171500_btc_v17",
  "asset": "BTC",
  "as_of": "2026-08-03T17:15:00Z",
  "computed_at": "2026-08-03T17:15:03Z",
  "data_cutoff_at": "2026-08-03T17:15:00Z",
  "direction_score": 34.7,
  "fragility_score": 62.1,
  "confidence_score": 78.4,
  "regime": "leveraged_risk_on",
  "feature_version": "features-v5",
  "scoring_version": "score-v3",
  "source_snapshots": {},
  "stale_sources": []
}
```

Her sinyal, kullandığı `snapshot_id` ile kaydedilmeli.

**Etkilenen bileşen:** btc-radar, radar-signal, karar günlüğü
**Uyumlu olduğu ilke:** Determinizm, test edilebilirlik, açıklanabilirlik
**Doğrulama testi:** Aynı ham veri snapshot'ı ve aynı commit hash'i 100 kez replay edildiğinde sinyal, skor, gerekçe ve invalidasyon bire bir aynı çıkmalı.

---

## 1.2 MCP iç servis protokolü olmamalı

MCP katmanı insan veya LLM tarafından sorgulama için faydalı. Fakat `radar-signal` doğrudan MCP araçlarına bağımlı olmamalı.

Daha temiz yapı:

```text
Core domain service
├── Versioned HTTP API
├── MCP adapter
├── CLI adapter
└── Offline replay adapter
```

Böylece MCP yalnızca bir sunum/adaptör katmanı olur. Sinyal motorunun çalışma zamanı sözleşmesi versioned HTTP API veya doğrudan kütüphane sözleşmesi olur.

**Etkilenen bileşen:** btc-radar
**İlke:** Determinizm ve test edilebilirlik
**Test:** MCP, HTTP ve offline replay aynı snapshot için aynı domain sonucunu üretmeli.

---

## 1.3 En büyük kavramsal mimari sorunu: BTC rejimi ile ETH rejimi

Ürün BTC ve ETH sinyali üretiyor; fakat rejim beynindeki önemli kaynakların çoğu BTC'ye özgü:

* STH-SOPR
* CDD
* BTC kohortları
* BTC exchange flow
* CBBI
* BTC dominansı
* BTC balina davranışı

Bunlar ETH üzerinde etkili piyasa bağlamı sağlayabilir ama **ETH'ye ait yön veya kırılganlık skoru değildir**.

Tek bir `btc-radar` skorunun ETH sinyalini bloke etmesi şu tür hatalara yol açabilir:

* BTC sakin, ETH'ye özel güçlü bir gelişme var → ETH sinyali gereksiz filtrelenir.
* BTC on-chain riskli, ETH spot talebi kuvvetli → iki farklı durum tek skora sıkışır.
* ETH/BTC paritesi hareket ediyor fakat BTC/USD sakin → sistem rejimi göremez.

### Önerilen üç katman

```text
Global Crypto Regime
├── Makro olaylar
├── Genel likidite
├── BTC dominance
├── Piyasa genişliği
└── Genel türev kaldıraç

BTC Asset Regime
├── BTC spot/perp
├── BTC OI/funding
├── BTC on-chain
└── BTC premium/flows

ETH Asset Regime
├── ETH spot/perp
├── ETH OI/funding
├── ETH/BTC
├── ETH-specific flow/activity
└── ETH premium/spot demand
```

ETH sinyali:

```text
ETH final regime =
    global_crypto_regime
  + ETH_asset_regime
  + BTC_leadership_context
```

olmalı; doğrudan BTC skoru olmamalı.

**Etkilenen bileşen:** btc-radar scoring engine
**İlke:** Açıklanabilirlik ve test edilebilirlik
**Test:** BTC ve ETH rejim filtrelerinin ayrı ayrı ablation testi; ETH performansının yalnız BTC skoru, yalnız ETH skoru ve birleşik skor altında kıyaslanması.

---

## 1.4 Telegram ve HTTP operasyonel tekil hata noktaları

Şu an görünür SPOF'lar:

* btc-radar HTTP servisi
* Telegram teslimatı
* zamanlayıcı
* dry-run pozisyon veritabanı
* ana fiyat sağlayıcısı
* makine saati / clock drift
* Binance ağırlıklı veri hattı

Sinyal üretildiği halde Telegram'a ulaşmazsa sistem bunu "sinyal gönderildi" olarak kaydetmemeli.

### Outbox yaklaşımı

```text
SIGNAL_CREATED
    ↓
NOTIFICATION_PENDING
    ↓
TELEGRAM_SENT
    ↓
TELEGRAM_ACKNOWLEDGED veya DELIVERY_UNKNOWN
```

Aynı mesaj retry edilirse iki bildirim gitmemesi için `signal_id` tabanlı idempotency olmalı.

**Etkilenen bileşen:** bildirim ve pozisyon yaşam döngüsü
**İlke:** Determinizm, güvenilirlik
**Test:** Telegram bağlantısı 10 dakika kesildiğinde sinyaller kaybolmamalı, bağlantı geldiğinde birer kez gönderilmeli.

---

## 1.5 Strateji çatışma çözücüsü eksik

Aynı anda:

* S-0002 BTC long,
* başka strateji BTC short,
* ETH momentum long,
* global rejim risk-off

üretebilir.

Dokümanda en fazla üç stratejinin yayında olması belirtilmiş ancak **aynı varlıkta çelişen sinyallerin nasıl sunulacağı açıklanmıyor**.

Bir `Signal Arbiter` katmanı gerekli:

```text
Candidate signals
    ↓
Conflict detection
    ↓
Independent / Confirmed / Conflicted / Suppressed
    ↓
Final alert
```

Çelişkili sinyaller gizlenmek zorunda değil. Kullanıcıya şu şekilde sunulabilir:

```text
DURUM: ÇELİŞKİLİ

Momentum modeli: LONG
Jump-reversal modeli: SHORT
Rejim: nötr
Sonuç: Yeni yönsel sinyal üretilmedi
```

**Etkilenen bileşen:** radar-signal
**İlke:** Açıklanabilirlik
**Test:** Aynı varlık ve aynı mumda ters sinyaller üretildiğinde önceden tanımlanmış politika deterministik biçimde uygulanmalı.

---

# 2. İstatistiksel değerlendirme

## 2.1 DSR + purged walk-forward iyi ama yeterli değil

Deflated Sharpe Ratio, purged walk-forward ve embargo ciddi artılar. Ancak hâlâ şu seçim kanalları açık:

1. İnsan tarafından yapılan manuel parametre değişiklikleri
2. Claude/Codex tarafından önerilen varyantlar
3. Reddedilen eşikler
4. Stratejinin hangi veri kaynağını kullanacağına ilişkin seçimler
5. Filtre ekleme/çıkarma denemeleri
6. BTC'de başarılı olduğu için ETH'ye taşınması
7. Aynı OOS dönemine tekrar tekrar bakılması
8. Yayına alınacak üç stratejinin sonradan seçilmesi

DSR hesaplanırken yalnız Hyperopt deneme sayısını kullanmak yeterli değildir. **Tüm araştırma evrenindeki fiilî deneme sayısı** hesaba katılmalı.

### Experiment Registry gerekli

Her deney otomatik olarak kaydedilmeli:

```text
experiment_id
hypothesis_id
strategy_version
feature_set_version
parameter_hash
dataset_snapshot
train_period
validation_period
test_period
cost_model_version
result
accepted/rejected
parent_experiment
created_by
```

Claude'un önerdiği fakat başarısız olan on varyant da burada bulunmalı.

**Etkilenen bileşen:** strateji fabrikası
**İlke:** Test edilebilirlik ve yayın yanlılığına karşı koruma
**Test:** DSR'nin kullandığı deneme sayısının experiment registry'deki gerçek strateji ailesi denemeleriyle eşleşmesi.

---

## 2.2 Aynı holdout'a tekrar bakmak holdout'u eğitim setine çevirir

"Son altı ay Hyperopt'a kapalı" iyi bir kural. Ancak ekip sonuçları gördükten sonra:

* threshold değiştirirse,
* filtre eklerse,
* çıkış süresini değiştirirse,
* stratejiyi tekrar aynı altı ay üzerinde çalıştırırsa,

bu dönem artık gerçek out-of-sample değildir.

Daha doğru yapı:

```text
Development set
Validation set
Locked test set
Forward live quarantine
```

Locked test sonucu bir kez açılmalı. Sonradan değişiklik yapılırsa yeni bir gelecek dönemi beklenmeli veya nested walk-forward kullanılmalı.

**Etkilenen bileşen:** backtest protokolü
**İlke:** Test edilebilirlik
**Test:** CI, test dönemi açıldıktan sonra strateji kodunda değişiklik yapılmışsa eski OOS sonucunu "final" kabul etmemeli.

---

## 2.3 "En az 100 OOS işlem" tüm stratejilere uygulanamaz

Momentum stratejisi için 100 işlem düşük bile olabilir. Fakat FOMC stratejisi için 100 bağımsız olay toplamak yıllar sürer.

Ayrıca BTC ve ETH'nin aynı FOMC olayındaki işlemleri iki bağımsız gözlem değildir.

Strateji ailelerine göre kabul kriterleri ayrılmalı:

| Strateji ailesi    | Doğru örneklem birimi            |
| ------------------ | -------------------------------- |
| Momentum           | İşlem ve bağımsız piyasa epizodu |
| Mean reversion     | Şok olayı                        |
| FOMC               | FOMC açıklaması                  |
| Seans kırılması    | Gün/seans                        |
| Expiry             | Vade olayı                       |
| Likidasyon kaskadı | Bağımsız kaskad olayı            |

FOMC için "100 işlem" yerine örneğin:

* minimum bağımsız olay sayısı,
* matched placebo pencereleri,
* olay yönüne göre alt grup,
* BTC ve ETH korelasyon düzeltmesi,
* event-clustered standart hata

daha anlamlı olur.

**Etkilenen bileşen:** kabul kapıları
**İlke:** Bilimsel test edilebilirlik
**Test:** Her strateji ailesinin örneklem birimi ve minimum kanıt şartı ayrı şemada tanımlanmalı.

---

## 2.4 Efektif işlem sayısı ham işlem sayısından küçüktür

Arka arkaya gelen dört BTC long sinyali bağımsız dört deney olmayabilir. Aynı trendin parçalarıdır.

Bu nedenle:

```text
100 işlem ≠ 100 bağımsız gözlem
```

Blok bootstrap, event clustering veya effective sample size kullanılmalı.

Özellikle:

* aynı gün içindeki işlemler,
* BTC ve ETH eş zamanlı sinyalleri,
* aynı FOMC olayındaki işlemler,
* aynı likidasyon kaskadındaki girişler

tek küme olarak ele alınmalıdır.

---

## 2.5 PBO veya Reality Check eklenmeli

DSR'ye ek olarak en az bir seçim yanlılığı testi öneririm:

* Probability of Backtest Overfitting / CSCV
* White's Reality Check
* Hansen SPA

Bunların tamamını kullanmak zorunlu değil. Fakat yüzlerce varyant arasından en iyisini seçiyorsan yalnız Sharpe düzeltmesi yeterli koruma sağlamayabilir.

**Etkilenen bileşen:** strateji kabul pipeline'ı
**İlke:** Test edilebilirlik
**Test:** En iyi görünen stratejinin alternatif spesifikasyonlar karşısında şans eseri seçilmiş olma ihtimali raporlanmalı.

---

## 2.6 Point-in-time veri zorunlu

Canlı API'den geçmiş funding, OI veya on-chain veri çekmek tehlikelidir. Sağlayıcı:

* geçmiş veriyi düzeltebilir,
* metodolojiyi değiştirebilir,
* eksik gözlemleri sonradan backfill edebilir,
* timestamp'i normalize edebilir.

Backtest, bugün indirilen "düzeltilmiş geçmiş" ile yapılırken canlı sistem geçmişte o değeri hiç görmemiş olabilir.

Her ham veri şu bilgilerle saklanmalı:

```text
event_time
available_at
ingested_at
provider
provider_schema_version
raw_payload_hash
```

Özellikle `available_at` çok önemli:

> Bu veri ekonomik olarak hangi zamanı anlatıyor değil, sistem tarafından ilk kez hangi anda bilinebiliyordu?

**Etkilenen bileşen:** btc-radar veri deposu
**İlke:** Determinizm ve look-ahead yasağı
**Test:** Backtest yalnız `available_at <= decision_time` verilerini okuyabilmeli.

---

## 2.7 Rejim filtresi de overfit olabilir

A/B/C karşılaştırması çok iyi:

* çıplak
* +rejim
* +rejim+karartma

Ancak rejim eşiği `60`, güven eşiği `55`, funding z-skoru veya blackout penceresi performansa bakılarak seçilirse filtre de strateji kadar overfit olur.

Rejim katmanının ayrı bir hipotez ve deney kimliği olmalı.

Ayrıca rejim filtresi yalnız Sharpe'a göre değerlendirilmemeli:

* maksimum drawdown
* tail loss
* false-negative oranı
* kaçırılan güçlü işlemler
* turnover
* rejim başına performans
* coverage kaybı

da ölçülmeli.

---

# 3. İki hızlı çıkış modeli yeterli mi?

## Hüküm: Mantıklı ama `--timeframe-detail 1m` tek başına yeterli değil

Kavramsal ayrım doğru:

* Fikir değişimi → kapanmış mumla çıkış
* Acil koruma → daha hızlı fiyat döngüsü

Fakat 5 saniyelik canlı kontrolü 1 dakikalık backtest verisiyle tam olarak yeniden üretmek mümkün değildir.

Bir dakikalık mum bize yalnız şunları verir:

```text
open
high
low
close
```

Şunu vermez:

```text
Önce stop mu görüldü?
Önce hedef mi görüldü?
Fiyat hangi sıra ile hareket etti?
Trailing stop hangi saniyede yükseldi?
Gerçek spread neydi?
```

Aynı dakika içinde hem stop hem hedef görülürse sonuç belirsizdir.

### Üç seçenek

1. Event-sensitive stratejiler için 1 saniye veya trade-level veri kullanmak
2. Belirsiz mumlarda daima kötü senaryoyu seçmek
3. Mum içi yolu Monte Carlo/bridge yaklaşımıyla simüle edip sonuç aralığı vermek

İlk aşamada en güvenli seçenek:

> Aynı detay mumunda hem stop hem hedef görülürse stop önce çalışmış kabul edilir.

Bu muhafazakâr olur.

---

## 3.1 Giriş fiyatı mum kapanışı olmamalı

Sinyal mum kapanınca hesaplanıyorsa kullanıcı veya sistem aynı mumun kapanış fiyatından işlem yapamaz.

Gerçekçi referans giriş:

```text
signal_decision_time
+ hesaplama gecikmesi
+ API gecikmesi
+ Telegram gecikmesi
+ varsayılan insan reaksiyonu
```

Sistem defteri için en azından:

* sonraki trade,
* sonraki mum açılışı,
* bid/ask tarafı,
* tanımlı latency

kullanılmalı.

Aksi takdirde özellikle 15 dakikalık breakout stratejilerinde sinyal kapanış fiyatı iyimser olur.

**Etkilenen bileşen:** dry-run ledger ve backtest
**İlke:** Test edilebilirlik
**Test:** 0, 2, 5, 15 ve 30 saniyelik giriş gecikmesi altında performans hassasiyeti.

---

## 3.2 "Koruyucu çıkış" ifadesi dikkatli kullanılmalı

Sistem emir göndermediği için 5 saniyelik kontrol kullanıcının gerçek zararını durdurmaz. Yalnızca sistemin ideal pozisyon defterini kapatır ve bildirim üretir.

Bu yüzden mesaj dili:

```text
STOP ÇALIŞTI — pozisyon kapandı
```

yerine daha doğru biçimde:

```text
SİSTEM İNVALIDASYONU TETİKLENDİ
Referans fiyat stop seviyesini geçti.
Gerçek pozisyonunuz otomatik olarak kapatılmadı.
```

olmalı.

Aksi halde ürün, emir göndermediği hâlde psikolojik olarak risk koruması sağlıyormuş gibi algılanabilir.

---

## 3.3 Yaşam döngüsü açık bir state machine olmalı

Önerilen durumlar:

```text
CANDIDATE
├── BLOCKED
├── EXPIRED
└── APPROVED
      ↓
SIGNAL_SENT
      ↓
REFERENCE_OPEN
├── INVALIDATED
├── STRATEGY_EXIT
├── STOP_EXIT
├── ROI_EXIT
├── TIME_EXIT
└── DATA_FAILURE_EXIT
      ↓
CLOSED
```

Her geçiş:

* idempotent,
* timestamp'li,
* sebep kodlu,
* önceki durum kontrollü

olmalı.

Özellikle mum kapanışı ile 5 saniyelik stop kontrolü aynı anda çalışırsa hangi çıkış sebebinin öncelikli olduğu tanımlanmalı.

---

# 4. Rejim skorlaması değerlendirmesi

Mevcut formül iyi bir ilk prototip:

```text
d × q × f × u × weight
```

Fakat beş önemli zayıflığı var.

## 4.1 Eksik veri kalan kaynakları güçlendirebilir

Formül yalnız mevcut ağırlıkların toplamına bölünüyorsa altı kaynak düştüğünde kalan iki kaynak toplam skoru tamamen belirleyebilir.

Güven skoru düşer ama yön skoru yine `+80` görünebilir.

Bu psikolojik olarak sorunlu:

```text
Yön: +80
Güven: 35
```

Kullanıcı çoğu zaman +80'e odaklanır.

### Öneri: nötre shrinkage

```text
raw_score = mevcut veriden hesaplanan skor
coverage = güvenilir mevcut aile kapsamı

adjusted_score = raw_score × coverage
```

Veri azaldıkça yön skoru da sıfıra yaklaşmalı.

---

## 4.2 Metrik sayısı fazla olan aile baskın olabilir

On-chain ailesinde on metrik, premium ailesinde iki metrik varsa on-chain doğal olarak daha fazla oy kazanabilir.

Metrik seviyesinden doğrudan global skora gitmek yerine:

```text
Metric scores
    ↓
Family score
    ↓
Global score
```

kullanılmalı.

Her veri ailesinin maksimum katkısı sınırlandırılmalı:

* türevler
* spot talep
* on-chain
* piyasa genişliği
* makro/olay
* volatilite
* likidite

Bu, çift sayım problemini `u` katsayısından daha açıklanabilir hâle getirir.

---

## 4.3 `d = −2…+2` gerçekte ordinal bir ölçek

`+2`, `+1`'in tam iki katı kanıt anlamına gelmeyebilir. Fakat formül bunu iki kat kabul ediyor.

Bu nedenle her metriğin tarihsel forward-return dağılımıyla kalibre edilmesi gerekir.

Örneğin:

```text
Funding d=+2
```

etiketi yerine:

```text
Bu funding koşulunda sonraki 4 mumun
medyan getirisi: +0,12%
pozitif olasılığı: %54
örneklem: 428
```

gibi bir calibration tablosu üretilebilir.

Skor yine deterministik ve açıklanabilir kalır.

---

## 4.4 Etkileşimleri yakalamıyor

Şunların her biri ayrı ayrı güçlü olmayabilir:

* funding yüksek
* OI yükseliyor
* fiyat yeni zirve yapamıyor

Ama üçü birlikte önemli bir kırılganlık durumu oluşturabilir.

Doğrusal toplama bu etkileşimi zayıf yakalar.

Kara kutu ML zorunlu değil. Açıklanabilir interaction rules yeterlidir:

```text
IF funding_extreme
AND oi_expanding
AND price_momentum_stalling
THEN fragility += 2
```

Bu kurallar da hipotez kartı ve backtestten geçmelidir.

---

## 4.5 Rejim chattering riski

Skor eşik civarında hareket ederse:

```text
59 → 61 → 58 → 62
```

rejim sürekli değişebilir.

Öneriler:

* giriş ve çıkış için farklı eşikler
* minimum rejim kalış süresi
* exponentially weighted smoothing
* değişim hızı filtresi
* transition state

Örnek:

```text
Riskli rejime giriş: fragility ≥ 65
Riskli rejimden çıkış: fragility ≤ 50
```

**Test:** Bir günde kaç rejim değişimi oluştuğu ve bu geçişlerin forward volatility ile ilişkisi ölçülmeli.

---

## 4.6 Skorun açıklaması tek taraflı olmamalı

Telegram mesajında yalnız "neden sinyal geldi?" değil, "sinyale karşı hangi kanıtlar var?" da bulunmalı.

Örnek:

```text
Destekleyen:
+ Hacim 60 günlük saatlik medyanın 1,8 katı
+ 1h aralığı yukarı kırıldı
+ Spot CVD pozitif

Karşı çıkan:
- Funding %96 persentilde
- OI son 4 saatte %7 arttı
- Kırılganlık skoru 64
```

Bu, açıklamayı satış metni olmaktan çıkarıp karar desteğine dönüştürür.

---

# 5. Ürün açısından eksik kritik özellikler

## 5.1 "İşlem yok" durumu birinci sınıf çıktı olmalı

Sinyal gelmemesi kullanıcıya hiçbir şey anlatmaz:

* Sistem çalışmıyor olabilir.
* Veri eksik olabilir.
* Setup oluşmamış olabilir.
* Setup blackout tarafından engellenmiş olabilir.
* Stratejiler çelişmiş olabilir.

Bu nedenle periyodik veya sorgulanabilir durum kartı gerekli:

```text
BTC — NO TRADE

Rejim: sıkışmalı nötr
Beklenen tetik:
• 1h range kırılımı
• hacim z-score > 1.5

Engeller:
• hacim yetersiz
• funding nötr
• momentum teyidi yok

Veri sağlığı: 9/10 kaynak güncel
```

Bu ürünün güvenilirliğini ciddi biçimde artırır.

---

## 5.2 Sinyal son kullanma zamanı

15 dakikalık intraday sinyal 40 dakika sonra aynı sinyal değildir.

Her sinyal şunları taşımalı:

```text
valid_from
valid_until
maximum_entry_deviation
cancel_condition
```

Örneğin:

```text
Referans giriş: 64.200–64.350
Geçerlilik: 20:30'a kadar
Fiyat 64.700 üzerinde giriş yapılırsa setup artık geçerli değil
```

---

## 5.3 Sinyal kimliği ve replay

Her bildirimde kısa bir sinyal kimliği bulunmalı:

```text
BTC-S0002-20260803-1715-L-01
```

Bu kimlikten şu bilgiler geri getirilebilmeli:

* ham veri snapshot'ı
* strateji sürümü
* parametre sürümü
* rejim snapshot'ı
* gerekçe
* sonradan gerçekleşen MFE/MAE
* çıkış nedeni
* kullanıcının kararı

Bu hem QA hem araştırma açısından projenin en değerli özelliklerinden biri olabilir.

---

## 5.4 Karar günlüğü Telegram UX'ine bağlanmalı

Bildirim butonları:

```text
[İşleme Girdim]
[Atladım]
[Geç Gördüm]
[Kararsızdım]
```

İşleme girdim seçilirse:

```text
Gerçek giriş fiyatı
Pozisyon büyüklüğü
Kaldıraç
Kullanıcının stop seviyesi
```

kaydedilebilir.

Böylece şu ayrım ölçülür:

```text
Sistem edge'i
− bildirim gecikmesi
− insan gecikmesi
− seçici işlem alma
− execution farkı
= kullanıcı sonucu
```

Dokümanda bu ayrım düşünülmüş; ürün arayüzüne taşınması kritik.

---

## 5.5 Veri sağlığı görünür olmalı

Her sinyalde en azından:

```text
Data health: 87/100
Stale: Korea Premium, 22 dakika
Unavailable: Coinbase spot depth
```

gibi bir satır bulunmalı.

"Güven 72" tek başına yeterli değil; neden düştüğü görünmeli.

---

# 6. İtiraf listesine eklenmesi gereken riskler

## 6.1 Açıklama kaynaklı otomasyon yanlılığı

İyi yazılmış gerekçe, zayıf bir sinyali gerçekte olduğundan daha ikna edici gösterebilir.

Açıklanabilirlik her zaman güvenilirlik değildir.

Özellikle kullanıcı:

* üç olumlu madde,
* net invalidasyon,
* profesyonel biçimlendirme

gördüğünde sistemin istatistiksel kanıtından daha fazla emin olabilir.

Çözüm: karşı kanıtlar, geçmiş benzer sinyal performansı ve örneklem büyüklüğü de sunulmalı.

---

## 6.2 Bildirim gecikmesi edge'i tüketebilir

Sinyal motoru doğru olsa bile:

```text
mum kapanışı
→ veri güncellemesi
→ skor hesaplama
→ Telegram
→ telefon bildirimi
→ insan kararı
```

zinciri 15 dakikalık stratejide avantajı silebilir.

Backtestte yalnız piyasa maliyeti değil, **decision latency** maliyeti de ölçülmeli.

---

## 6.3 Sağlayıcı metodoloji değişikliği

Üçüncü taraf provider aynı endpoint'i koruyup hesaplama yöntemini değiştirebilir. Schema testi bunu yakalamaz.

Dağılım izleme gerekli:

* ortalama
* standart sapma
* null oranı
* güncelleme sıklığı
* persentil dağılımı
* anormal sabit değer

---

## 6.4 USDT ve USD aynı şey değildir

Binance USDT perpetual, Coinbase USD spot ve farklı stablecoin piyasaları karşılaştırılıyorsa premium sinyali:

* gerçek türev premium'u,
* USDT depeg'i,
* borsa fiyat farkını,
* transfer kısıtını

birbirine karıştırabilir.

Spot-perp basis hesaplarında quote asset normalizasyonu yapılmalı.

---

## 6.5 Kullanıcı gerçek pozisyonu ile sistem defteri arasındaki ayrım büyüyebilir

Bu risk belgede var, fakat yalnız giriş gecikmesi değil:

* farklı kaldıraç,
* farklı borsa,
* farklı spread,
* kısmi pozisyon,
* stop değiştirme,
* erken çıkış,
* yeniden giriş,
* telefona erişememe

de fark yaratır.

Sistem performansı ve kullanıcı performansı kesinlikle aynı grafikte tek seri olarak gösterilmemeli.

---

## 6.6 Hukuki konumlandırma

Emir göndermemek otomatik olarak "yatırım tavsiyesi değil" sonucunu garanti etmez. Ürün yalnız kişisel kullanımda kalırsa risk başka, dağıtılır veya ücretlendirilirse başkadır.

Disclaimer tek başına yeterli hukuki kontrol değildir. Özellikle gelecekte üçüncü kişilere sunulacaksa ayrıca değerlendirilmelidir.

---

## 6.7 Üç aylık değerlendirme ve dört haftalık karantina yetersiz olabilir

Momentum stratejisi dört haftada onlarca sinyal üretebilir. FOMC stratejisi ise belki bir olay görür.

Karantina zaman bazlı değil, fırsat bazlı olmalı:

```text
minimum süre
AND minimum sinyal sayısı
AND minimum farklı rejim sayısı
AND minimum olay sayısı
```

---

# 7. Kırmızı çizgi kontrolü

Dokümanda doğrudan veya dolaylı birkaç çelişki bulunuyor.

## 7.1 Determinizm ↔ değişken canlı API verisi

Aynı mum için immutable snapshot belirtilmediği sürece aynı veri garanti edilemiyor.

**Durum:** Kritik çelişki
**Çözüm:** Snapshot ID, point-in-time veri ve replay deposu

---

## 7.2 FOMC stratejisi ↔ FOMC karartması

S-0004 içinde FOMC/seans kırılması bulunuyor; aynı zamanda FOMC karartma modülü var.

Karartma, FOMC stratejisinin kendi sinyalini de bloke edebilir.

Politika matrisi gerekli:

| Strateji               | FOMC öncesi    | İlk 15 dk      | Tanımlı post-event pencere |
| ---------------------- | -------------- | -------------- | -------------------------- |
| Normal momentum        | Blokla         | Blokla         | Temkinli aç                |
| Mean reversion         | Blokla         | Blokla         | Blokla/ayrı test           |
| FOMC-event strategy    | Armed          | Bekle          | İzin ver                   |
| Mevcut pozisyon çıkışı | Her zaman izin | Her zaman izin | Her zaman izin             |

Ayrıca **FOMC stratejisi ile normal seans breakout stratejisini ayırmanı** öneririm. Bunlar farklı veri üretim süreçleri:

* seans breakout: neredeyse günlük
* FOMC: seyrek, planlı makro şok

Tek strateji kimliği altında tutulmamalı.

---

## 7.3 Fail-closed ↔ "veri yetersiz damgası"

Dokümanda güven `<55` olduğunda "veri yetersiz damgası — fail-closed" deniyor.

Ancak iki farklı davranış olabilir:

1. Sinyal bloke edilir.
2. Sinyal gönderilir ama üstüne damga konur.

İkincisi fail-closed değildir.

Kesin politika tanımlanmalı:

```text
required data missing → BLOCK
optional data missing → SCORE SHRINK + WARNING
```

---

## 7.4 Altı aylık OOS ↔ üç aylık değerlendirme

Bilimsel protokolde son altı ay kapalı OOS olarak belirtilirken yol haritasında üç aylık veriye dayalı değerlendirme yazıyor.

Üç ay:

* farklı volatilite rejimlerini,
* yeterli FOMC olayını,
* hafta sonu yapısını,
* trend ve range dönemlerini

kapsamayabilir.

Bu iki madde uyumlandırılmalı.

---

## 7.5 Açıklanabilirlik ↔ yalnız `enter_tag` üzerinden gerekçe

`enter_tag → gerekçe` eşlemesi deterministiktir ama gerekçe yalnız önceden yazılmış şablonsa gerçek açıklama olmayabilir.

Gerçek açıklama şunları içermeli:

```text
Hangi özellik?
Gerçek değeri neydi?
Eşik neydi?
Hangi veri zamanı kullanıldı?
Hangi koşul başarısızdı?
```

Örneğin:

```text
"Hacim yüksek olduğu için momentum"
```

yerine:

```text
"Son 1 saat hacmi, aynı UTC saatinin 60 günlük medyanının 1,63 katıydı; giriş eşiği 1,25'ti."
```

---

# Önceliklendirilmiş düzeltme planı

## P0 — Yeni strateji eklemeden önce

1. **Immutable data/regime snapshot sistemi**
2. **BTC-global-ETH rejim ayrımı**
3. **Point-in-time ham veri deposu ve `available_at` alanı**
4. **Deney kayıt sistemi ve gerçek trial sayısı**
5. **Açık state machine + idempotent notification outbox**
6. **1m/5s execution tutarsızlığı için muhafazakâr simülatör**
7. **Strateji çatışma çözücüsü**
8. **FOMC stratejisi ile seans stratejisinin ayrılması**

## P1 — İlk anlamlı backtestten önce

1. PBO/SPA veya Reality Check eklemek
2. Gecikmeli giriş ve conditional slippage modeli
3. Aile bazlı kabul kriterleri
4. Blok bootstrap ve efektif örneklem
5. Rejim skorunda family aggregation ve missing-data shrinkage
6. Event calendar point-in-time sürümleme
7. USDT/USD quote normalizasyonu

## P2 — Dry-run ürün aşamasında

1. No-trade durumu
2. Sinyal geçerlilik süresi
3. Karşı kanıtların gösterilmesi
4. Veri sağlık satırı
5. Telegram karar butonları
6. Replay ekranı
7. Live/backtest parity raporu
8. Strateji ve rejim bazlı sinyal karnesi

---

# Ben olsam geliştirme sırasını nasıl değiştirirdim?

Şu sırayla ilerlerdim:

1. `S-0001` kontrol stratejisini ayağa kaldır.
2. Sinyal, snapshot, ledger ve Telegram yaşam döngüsünü uçtan uca bitir.
3. Aynı kayıtlı veriyle replay testini kur.
4. Giriş/çıkış simülatörünü gerçekçi hâle getir.
5. Experiment Registry'yi kur.
6. `S-0002` hacim-koşullu momentumu ilk gerçek edge adayı olarak ekle.
7. Rejim filtresini önce gözlem modunda çalıştır; sinyali bloke etmesin.
8. Yeterli örnek biriktikten sonra çıplak/+rejim kıyasını yap.
9. Seans breakout'u ayrı strateji olarak ekle.
10. FOMC stratejisini düşük frekanslı event-study pipeline'ına al.
11. Jump-reversal ve likidasyon kaskadını tick/trade-level veri olmadan üretime alma.

# Son karar

**Projeyi devam ettirmeye kesinlikle değer.** Temel ürün tezi, felsefesi ve araştırma yaklaşımı güçlü. En önemli başarı, henüz strateji yazmadan önce "yanlış başarıyı nasıl engellerim?" sorusunu sormuş olman.

Ancak şu aşamada yeni kaynak veya yeni indikatör eklemekten daha değerli iş, sistemin **kanıt zincirini** sağlamlaştırmak:

```text
Ham veri
→ o anda bilinen snapshot
→ feature sürümü
→ rejim sürümü
→ strateji kararı
→ gerçekçi referans fill
→ pozisyon state geçişleri
→ bildirim teslimatı
→ sonuç
→ replay
```

Bu zincirin her halkası sürümlü ve yeniden üretilebilir hâle geldiğinde RADAR, "iyi düşünülmüş bir trading bot projesi" olmaktan çıkıp gerçekten **denetlenebilir bir quant araştırma ve karar-destek platformuna** dönüşür.
