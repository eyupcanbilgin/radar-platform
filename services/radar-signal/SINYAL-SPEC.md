# SINYAL-SPEC.md — Radar Signal
**BTC & ETH Intraday Sinyal Servisi — Teknik Şartname v2.14**

> v2.14 (6 Ağu 2026): ADR-0031 ile ADR-0030'da ön-kayıtlı F-0001 forward tetik coverage
> gözlemi immutable/idempotent SQLite defteri ve exact-hour CLI olarak uygulandı. İlk gerçek
> kayıt ön-kayıt başlangıcından önce çalıştırılmadı. v2.13 → git geçmişi.

> v2.13 (6 Ağu 2026): ADR-0030 ile F-0001 sonuçsuz forward tetik coverage gözlemi,
> `2026-08-07T00:00:00Z` başlangıcıyla koddan önce ön-kayıt edildi. Geçmiş backfill,
> outcome, Registry, alert ve direction üretimi kapalıdır. v2.12 → git geçmişi.

> v2.12 (6 Ağu 2026): ADR-0029 ile mühürlü üç context setinden config-güdümlü F-0001
> veri/tetik readiness raporu eklendi. Rapor performans ölçmez, Registry'ye yazmaz, Locked
> OOS'u açmaz ve direction null kalır. v2.11 → git geçmişi.

> v2.11 (6 Ağu 2026): ADR-0028 ile F-0001 ilk gerçek Development koşusu iki venue'de
> 547 etiketlenebilir satır fakat 0/30 bağımsız tetik nedeniyle `unavailable` kaydedildi.
> Registry'nin kapalı verdict sözlüğünde etkin kayıt `invalid (unavailable evidence)` olur;
> bu performans reddi değildir. Eşikler değiştirilmedi, Locked OOS açılmadı ve direction
> null kaldı. v2.10 → git geçmişi.

> v2.10 (6 Ağu 2026): ADR-0027 ile F-0001 event-row adaptörü gerçek
> `decision-context/v1` alan yerleşimine bağlandı; ilk gerçek girişim metrik ve Registry
> kaydı üretmeden fail-closed durmuştu. Ön-kayıt veya ölçüm kuralı değişmedi. v2.9 → git geçmişi.

> v2.9 (6 Ağu 2026): ADR-0026 ile gerçek Coinbase geçmişinde doğrulanan iki venue gap'i
> mum uydurmadan kesintisiz segmentlere ayrılır; gap'e temas eden etiket pencereleri dışlanır
> ve coverage evidence'a yazılır. F-0001 hâlâ ölçülmedi. v2.8 → git geçmişi.

> v2.8 (6 Ağu 2026): Signal ADR-0025 ve platform sözleşmesiyle F-0001 runner, ana ve iki
> ablation context klasörünün `f0001-context-set/v1` variant/sınır/dosya hash manifestini
> doğrulamadan ölçüm yapmaz. Gerçek ölçüm yapılmadı. v2.7 → git geçmişi.

> v2.7 (6 Ağu 2026): ADR-0024 ile F-0001 gerçek Development koşusu için manifest
> doğrulamalı, iki zorunlu leave-one-family-out ablation girdili ve Registry'de mükerrer
> kanıtı engelleyen fail-closed orkestratör eklendi. Gerçek ölçüm yapılmadı. v2.6 → git geçmişi.

> v2.6 (5 Ağu 2026): ADR-0023 ile public Coinbase BTC-USD 1h kapalı mum indiricisi ve
> Binance/Coinbase dosyalarını birlikte kapsayan çok-venue manifest üretimi eklendi.
> Ham veri ve gerçek F-0001 ölçümü repoya alınmadı. v2.5 → git geçmişi.

> v2.5 (5 Ağu 2026): ADR-0022 ile PIT context ve saatlik venue OHLCV'den provenance bağlı
> F-0001 event-row üreticisi eklendi. Gerçek veri ölçümü yapılmadı. v2.4 → git geçmişi.

> v2.4 (5 Ağu 2026): ADR-0021 ile F-0001 için train-only Laplace olasılıklı pooled
> out-of-fold kalibrasyon çekirdeği eklendi. Tetik/etiket üretimi ve gerçek ölçüm yapılmadı.
> v2.3 → git geçmişi.

> v2.3 (5 Ağu 2026): F-0001 yönsüz kırılganlık → +24h volatilite genişlemesi hipotezi,
> sonuç görülmeden `config/fragility_calibration.yaml` ile ön-kayıt edildi ve v1.1'de
> out-of-fold olasılık/Brier formülü sıkılaştırıldı. Ölçüm yapılmadı.
> v2.2 → git geçmişi.

> v2.2 (5 Ağu 2026): Platform ADR-0004 ile ürün v1 kırılganlık/volatilite uyarısı odağına
> alındı; yönsel araştırma park edildi ve aktif runtime `direction=null`/`WAIT` olarak
> sabitlendi. v2.1 → git geçmişi.

> v2.1 (5 Ağu 2026): ADR-0020 ile Faz 2 dönem/venue kırılganlık kapısı eklendi;
> istatistik rapor sözleşmesi `phase2-statistical-gates/v2` oldu. Gerçek veri ölçümü
> yapılmadı. v2.0 → git geçmişi.

> v2.0 (5 Ağu 2026): ADR-0019 ile Faz 2 DSR, PBO/CSCV, config-güdümlü ±%20
> parametre hassasiyeti ve eşleşmiş-fold veri ailesi ablation kapıları eklendi. Reddedilmiş
> hipotezler geriye dönük yeniden ölçülmedi. v1.9 → git geçmişi.

> v1.9 (5 Ağu 2026): ADR-0018 ile S-0004 (Volatilite Rejimi Koşullandırmalı Trend) hipotezinin
> sızıntısız Purged Walk-Forward Development ölçüm sonuçları ve REDDEDİLDİ kararı işlendi.
> v1.8 → git geçmişi.

> v1.8 (5 Ağu 2026): ADR-0017 ile S-0003 (Aşırı Settled Funding) hipotezinin sızıntısız
> Purged Walk-Forward Development ölçüm sonuçları ve REDDEDİLDİ (REJECTED) kararı işlendi.
> v1.7 → git geçmişi.

> v1.7 (5 Ağu 2026): ADR-0016 ile Faz 2 referans taban çizgileri (`cash`, `buy_and_hold`,
> `simple_trend`) maliyet sonrası değerlendiricisi (`scripts/baseline_evaluator.py`) eklendi.
> v1.6 → git geçmişi.

> v1.6 (5 Ağu 2026): ADR-0014 ile Purged Walk-Forward + Embargo split ve ölçüm protokolü,
> config güdümlü eşikler, fail-closed Locked OOS kuralı ve `scripts/walk_forward.py` eklendi.
> v1.5 → git geçmişi.

> v1.5 (4 Ağu 2026): Public Binance USD-M kapalı mum adaptörü, exact-hour context JSON
> inbox ve UTC tek-sefer/daemon paper runtime eklendi. v1.4 → git geçmişi.

> v1.4 (4 Ağu 2026): BTCUSDT 1h teknik FeatureSnapshot, birinci sınıf WAIT karar kartı ve
> atomik append-only DecisionLedger eklendi. v1.3 → git geçmişi.

> v1.3 (4 Ağu 2026): İlk ürün dilimi BTCUSDT 1h paper olarak daraltıldı ve
> `decision-context/v1` tüketici/fail-closed sözleşmesi eklendi. v1.2 → git geçmişi.

> v1.2 (4 Ağu 2026): ADR-0007 ile eleme istatistiği v2 kapıları ve S-0002b kanıt
> düzeltmesi işlendi. v1.1 → git geçmişi.

| Alan | Değer |
|---|---|
| Proje sahibi | Eyüpcan |
| Tarih | 3 Ağustos 2026 |
| Çalışma adı | `radar-signal` (aynı monorepodaki btc-radar servisinin kardeş bileşeni) |
| Karar seti | BTC 1h kırılganlık/volatilite uyarısı + veri blocker'ı · direction null · emir YOK |
| İlişkili proje | `btc-radar-mcp` — Faz D'de rejim filtresi olarak entegre edilir |

> **Yasal ve etik çerçeve:** Bu sistem emir göndermez, borsa hesabına yazma yetkisiyle
> bağlanmaz, yatırım tavsiyesi değildir. Ürün v1 çıktısı "kırılganlık uyarısı + gerekçe +
> veri blocker'ı"dır; işlem kararı ve sorumluluğu kullanıcıya aittir. Bu metin her bildirim
> şablonunun altında yer alır.

---

## 1. Ürün Tanımı

### 1.1 Ne yapar
Ürün v1, BTCUSDT için kapanmış 1h veri ve point-in-time context üzerinden deterministik
kırılganlık, volatilite genişlemesi riski, veri güveni ve blocker uyarısı üretir; açıklamasını
ledger/outbox üzerinden bildirir ve ileri gerçekleşen sonuçları ölçer. Yön ölçülmediği için
aktif runtime kararı `WAIT`, direction değeri `null`dır.

### 1.2 Ne yapmaz
- Emir göndermez; API anahtarı sadece public veri için (veya hiç — freqtrade public mumlarla çalışır).
- LLM canlı sinyal döngüsünde yer almaz. Sinyal = deterministik Python. AI'ların rolü: strateji yazımı, backtest analizi, rejim bağlamı.
- "Kesin al/sat" dili kullanmaz; her sinyal koşullu ve invalidasyonlu ifade edilir.
- Kabul edilmiş yeni yönsel setup yokken LONG/SHORT veya nötr yön skoru üretmez.

### 1.3 Başarı tanımı (kusursuzluk değil)
Ürün v1 başarısı kârlılık veya yön isabetiyle değil; kırılganlık olaylarının ileri
volatilite/MAE ile kalibrasyonu, precision/recall, lead time, false-alarm, abstention ve veri
kapsamıyla ölçülür. Eksik sonuç sakin piyasa sayılmaz. Aşağıdaki yönsel strateji kapıları
araştırma arşivi ve gelecekteki yeniden-açma koşulu olarak korunur:

Bir strateji ancak şu beşini aynı anda sağlarsa "yayında" kalır:
1. **Maliyet sonrası pozitif beklenti:** komisyon + kayma + funding (`config/costs.yaml`, CR-5) düşüldükten sonra out-of-sample dönemde pozitif getiri.
2. **İstatistiksel asgari:** out-of-sample'da ≥100 işlem — bu eşik **yüksek-frekans strateji aileleri** içindir; olay-bazlı ailelerde (FOMC, seans) örneklem birimi aileye göre tanımlanır (CR-002 P1-2: olay sayısı + placebo pencere, event-clustered SE).
3. **Risk sınırı:** out-of-sample max drawdown, aynı dönem buy&hold drawdown'ından kötü değil.
4. **Deflated Sharpe (veri-tarama düzeltmesi):** eşik taraması/hyperopt yapılan her stratejide denenen konfigürasyon sayısı Experiment Registry'den alınır ve out-of-sample Sharpe, Deflated Sharpe Ratio (Bailey & López de Prado) ile düzeltilir. Düzeltme sonrası anlamlılık yoksa strateji **"şans" etiketiyle reddedilir** (CR-1).
5. **Çoklu maliyet senaryosunda hayatta kalma:** CR-5 senaryo matrisinin "gerçekçi" VE "taker ağırlıklı" satırlarında pozitif kalmak zorunlu; "stres" satırındaki çökme derecesi risk notu olarak raporlanır, ret nedeni değildir (CR-1).

---

## 2. Mimari

F-0001 araştırma girdisi iki bağımsız venue gerektirir. Binance futures verisi mevcut
freqtrade indirme hattından, Coinbase spot BTC-USD verisi anahtarsız public CCXT yüzeyinden
alınır. Coinbase indiricisi yalnız tam kapanmış `1h` mumları, kesintisiz ve tekil bir zaman
aralığı olarak atomik biçimde `user_data/data/coinbase/spot/` altına yazar. Açık mum,
başlangıç/son eksikliği, gap, duplicate veya ilerlemeyen pagination fail-closed hatadır.
`data_manifest.py` artık `user_data/data/` altındaki tüm venue dosyalarını tek snapshot'ta
hashler; geçmiş manifestler değiştirilmez.

```
[ Binance USDT-M public verisi (ccxt / freqtrade dahili) ]
        ▼
[ freqtrade çekirdeği ]  — dry-run modu (emir yok, hipotetik defter)
   ├─ user_data/strategies/   ← bizim yazdığımız strateji sınıfları (TEK üretim noktası)
   ├─ backtesting + hyperopt  ← strateji fabrikasının test bankosu
   └─ Telegram + webhook      ← sinyal + gerekçe teslimatı
        ▼
[ blackout modülü ]  — planlı olay takvimi (FOMC, CPI, büyük vade/expiry;
   kaynak: ekonomik takvim + Deribit expiry takvimi) → olay penceresinde yeni sinyal
   üretimi susturulur, Telegram'a "karartma aktif" bildirimi düşer. Varsayılan pencere:
   olay öncesi 30 dk + sonrası 60 dk (config/blackout.yaml). Gerekçe: Kart K — FOMC
   sonrası ilk saatte BTC mutlak getirisi ~2×, hacim ~2,5×; bu pencerede teknik sinyal
   gürültüdür (CR-2). Karartma-politika matrisi CR-002 P0-7: normal stratejiler bloklu,
   S-0005 "armed" bekler; AÇIK POZİSYON ÇIKIŞLARI HER ZAMAN İZİNLİ.
        ▼
[ rationale enricher ]  — webhook alıcısı (küçük FastAPI servisi; CR-002 yol haritası
   gereği yaşam döngüsüyle birlikte 2. sıraya öne çekildi — eski "Faz B sonu" planı geçersiz)
   sinyale ekler: tetikleyen koşullar (enter_tag), indikatör değerleri,
   (Faz D'den itibaren) btc-radar rejim/kırılganlık skoru
        ▼
[ Telegram kanalı ]  — insan-okur formatı; her mesajda gerekçe + invalidasyon + yasal not
```

Webhook ingress `/webhook/signal`, `/webhook/fill` ve `/webhook/exit` yollarında fail-closed
HMAC-SHA256 doğrulaması ister. İmzalanan byte dizisi
`timestamp + "." + nonce + "." + raw_body` biçimindedir; header'lar
`X-Radar-Timestamp`, `X-Radar-Nonce`, `X-Radar-Signature: sha256=<hex>` olarak taşınır.
Secret yalnız `RADAR_SIGNAL_WEBHOOK_SECRET` environment değeridir. Saat toleransı ve nonce
retention `config/lifecycle.yaml` içindedir. Doğrulanmış nonce ayrı SQLite store'a atomik
yazılır; tekrar 409, eksik/yanlış/bayat kimlik 401, sunucuda secret eksikliği 503 döner.
`/health` kimliksiz kalır ve secret bilgisi göstermez.

Freqtrade'in yerleşik webhook config'i dinamik imza header'ı üretmediğinden doğrudan uyumlu
sayılmaz. Freqtrade→enricher canlı bağlantısı ayrı bir yerel signer adaptörü eklenene kadar
kapalıdır; URL içine secret koymak veya imzasız fallback yasaktır.

**Veri sorumluluğu ayrımı:** Strateji/backtest mumunu freqtrade kendi CCXT katmanıyla çeker.
İlk BTC 1h standalone karar defteri de yeni bir HTTP provider yazmadan aynı sabitlenmiş CCXT
bağımlılığının `binanceusdm` public OHLCV yüzeyini kullanır. btc-radar provider'ları mum için
KULLANILMAZ. btc-radar'ın rolü yalnız rejim skorudur (OI/funding/on-chain bağlamı); çalışan
provider/HTTP context endpoint'i oluşana kadar taşıma exact-hour JSON inbox üzerinden yapılır.

**İlk ürün dilimi:** Platformun sözleşme kabiliyeti
`BTCUSDT · Binance USDT perpetual · kapanmış 1h mum · LONG/SHORT/WAIT` kapsamındadır;
Platform ADR-0004 uyarınca aktif ürün v1 profili yalnız `WAIT` ve direction-null kırılganlık
uyarısı üretir.
MCP rejim snapshot'ı `contracts/decision-context/v1` ile taşınır. Tüketici tam mum
`as_of` eşleşmesini ve `data_cutoff_at <= as_of` kuralını doğrular. Sözleşmedeki
`directional_decision_allowed=false` değeri yönsel sonucu kapatır ve `WAIT` üretir.
HTTP taşıması ve karar motoruna gerçek bağlama bu sözleşmeden sonraki ayrı iş paketidir.

### 2.1 BTC 1h karar çekirdeği

`decision_engine/`, kapanmış ve karar anında erişilebilir son 200 adet 1h mumdan
`FeatureSnapshotV1` üretir. Snapshot kimliği input digest+sürümden, content hash tüm
türetilmiş feature gövdesinden gelir. Eksik/gap history sessizce doldurulmaz; snapshot
`ready=false` ve açık eksik listesi taşır.

Her değerlendirilen saat `DecisionCardV1` üretir. Feature/context kapısı kapalıysa veya
yönsel setup yoksa sonuç `WAIT`tir. MCP direction skoru doğrudan LONG/SHORT yapılamaz.
Setup exact karar saati ve feature snapshot ID/hash'ine bağlıdır. Feature+context+karar
payload'ları `DecisionLedger` içinde tek transaction'la append-only saklanır; aynı saat
farklı içerikle UPDATE/DELETE/REPLACE edilemez. Ledger kartı girdilerden yeniden üretir ve
okumada kolon-payload tutarlılığını doğrular.

`scripts/run_hourly_decision.py`, public/anahtarsız Binance USD-M mumlarını exact 200 saatlik
pencerede alır ve Binance `serverTime` doğrulamalı, varsayılan 90 saniye kapanış gecikmesiyle
UTC slotunu işler. Borsa saati doğrulanmadan immutable slot dondurulmaz. Context yalnız
`var/decision-context/v1/BTCUSDT/1h/YYYY/MM/DD/HH.json` exact yolundan okunur; latest/önceki
saat fallback'i yoktur. Eksik/bozuk context veya mum erişim hatası saati atlamaz, değişmez
`WAIT` üretir. Açık `--as-of` replay/backfill'dir ve varsayılan ayrı replay ledger'ına yazar.
Daemon kodu hazırdır; MCP context producer, process supervision ve kesintisiz işletim kanıtı
henüz tamamlanmamıştır. Kabul edilmiş yönsel setup olmadığı için sağlıklı runtime çıktısı da
şimdilik `WAIT/no_directional_setup`tır.

### 2.2 Karar Sonuc Değerlendiricisi (Outcome Evaluator)

`decision_engine/outcomes.py` ve `evaluator.py`, her kaydedilmiş `DecisionCardV1` için
`+1h`, `+4h` ve `+24h` ufuklarında karar sonuçlarını ölçer.

1. **Ayrı ve Değişmez Defter (`decision_outcomes`):** Mevcut `hourly_decisions` ve
   `feature_snapshots` satırları asla değiştirilmez (ADR-0008). Outcome kayıtları ayrı
   `decision_outcomes` tablosunda append-only tutulur; UPDATE/DELETE ve çakışan INSERT
   SQLite trigger'larıyla engellenir.
2. **Kullanılabilir Mum ve Look-ahead Koruması:** Yalnız kapanmış ve
   `available_at_utc <= horizon_close_utc` olan public mumlar kullanılır. Açık mum,
   eksik mum veya gap ileriye doldurulmaz. Süresi dolmamış gelecek ufuklar `pending`,
   eksik/bozuk veriler `unavailable` olarak dürüstçe kaydedilir; sıfır/nötr getiri uydurulmaz.
3. **Semantik Idempotency ve Conflict Koruması:** Outcome kimliği `OUT-` ön eki ile
   `decision_id`, `horizon` ve `evaluator_version` alanlarından türetilir. Aynı veriyle
   tekrar çalıştırma idempotenttir (`recorded=False`). Farklı içerikle çakışan kayıt
   `ImmutableDecisionError` üretir.
4. **WAIT Semantiği:** `WAIT` birinci sınıf karardır. `WAIT` kararlarında yönsel `raw_return`,
   `net_return`, `MFE` ve `MAE` üretilmez (`None`). Piyasa hareketi açık semantikle
   `opportunity_return` $= (P_{end} - P_{ref}) / P_{ref}$ olarak kaydedilir.
5. **Maliyet Modeli Entegrasyonu:** LONG/SHORT net getirileri `config/costs.yaml` sözleşmesine
   göre komisyon ve kayma düşülerek hesaplanır; koda sabit eşik/maliyet gömülmez. Maliyet
   verisi eksikse net getiri hesaplanmaz (`None`).
6. **CLI Araçları:** `scripts/evaluate_decision_outcomes.py` script'i süresi dolmuş
   ufukları güvenli biçimde toplu olarak değerlendirir.

### 2.3 Saatlik Karar Teslimatı

Canlı `scripts/run_hourly_decision.py` her `DecisionCardV1` kaydından sonra değişmez ledger
payload'ından deterministik, insan-okur bir `hourly_decision` mesajı üretir ve ortak SQLite
outbox'a yazar. Runtime Telegram'a doğrudan bağlanmaz; mevcut `scripts/pump.py` PENDING
mesajları Telegram veya console göndericisine taşır. Açık `--as-of` replay tarihsel bildirim
üretmez ve `--outbox` ile birlikte kullanılamaz.

Teslimat idempotency anahtarı `(decision_id, "hourly_decision")` çiftidir. Aynı anahtar ve
bit-identical gövde güvenli tekrardır; farklı gövde hata verir. Ledger commit'i ile outbox
yazımı arasındaki süreç çökmesi iki yolla onarılır: aynı saat runtime tarafından yeniden
işlendiğinde `already_recorded` kartı tekrar kuyruğa alınır veya
`scripts/reconcile_hourly_delivery.py --limit N` en yeni, sınırlı karar kümesini tarar.
Sınırsız geçmiş taraması yoktur.

Mesaj; karar sonucu, gerekçeler, blocker'lar, veri sağlığı, uyarılar, feature/context snapshot
kimlikleri, `PAPER`, `real_orders=false` ve yasal notu taşır. `WAIT`, yön ya da nötr getiri
ölçümü iddiası değildir. Eksik veri blocker olarak görünmeye devam eder; teslimat katmanı
kararı veya yönü değiştiremez.

---

## 3. Strateji Fabrikası Protokolü

Bu projenin asıl ürünü tek bir strateji değil, **strateji üretme-test etme disiplinidir.** Her strateji şu hattan geçer:

**Registry değişmezliği:** İlk deney kaydı `registry/experiments.jsonl` dosyasına append
edilir. Sonradan bulunan kanıt veya uygulama hataları tarihî satırı yeniden yazmaz;
append-only `registry/verdict_events.jsonl` olayıyla etkin verdict'i düzeltir. DSR deneme
sayısı deney kayıtlarından gelir; verdict olayları yeni deneme sayılmaz.

1. **Hipotez kartı** (`docs/hypotheses/NNNN.md`): tek paragraf — hangi piyasa davranışını yakalıyor, neden var olmalı, hangi rejimde çalışması/çalışmaması beklenir.
2. **Claude Code implementasyonu:** freqtrade strateji sınıfı; her giriş koşulu ayrı `enter_tag` ile etiketlenir (gerekçe mekanizmasının temeli).
3. **Backtest protokolü (pazarlıksız):**
   - Veri: mevcut tüm 15m tarihçe; **train/test ayrımı** — son 6 ay yalnız out-of-sample, hyperopt ASLA görmez. Dönem disiplini CR-002 P1-3 ile derinleşir: Development / Validation / Locked-test / Forward-quarantine; locked sonuç bir kez açılır.
   - **Purged walk-forward** (CR-3, ADR-0014): `config/research_protocol.yaml` güdümlü; varsayılan 90 gün train, 30 gün test, 30 gün kaydırma; train/test sınırında en az 1 gün embargo boşluğu; forward horizon etiketi train sonunu aşıyorsa `train_purged_end_utc` ile temizlenir. Tüm zamanlar timezone-aware UTC zorunlu. Locked OOS dönemi (`2026-08-04T00:00:00Z`) varsayılan CLI ile kilitlidir ve erişilemez (`LockedOOSAccessError`). Boş/yetersiz veri pencereleri "0 getiri" sayılmaz; `unavailable`/`invalid` olarak raporlanır (`scripts/walk_forward.py`).
   - **BTC/ETH ayrı kalibrasyon** (CR-3): BTC'de geliştirilen parametre ETH'ye kopyalanmaz; ETH ayrıca bağımsız out-of-sample doğrulama seti olarak raporlanır.
   - **A/B/C kıyası zorunlu** (CR-3): her strateji (A) çıplak, (B) + rejim filtresi, (C) + rejim + karartma varyantlarıyla backtest edilir; filtre sonucu iyileştirmiyorsa o stratejide kullanılmaz — birleşim inanç değil ölçümdür.
   - **Zaman standardı** (CR-3): ham veri UTC; seans tanımları `Europe/London` / `America/New_York` timezone-aware (DST otomatik). Sabit İstanbul saatiyle seans tanımı yasak.
   - **Türev verisi yayın-anı kuralı** (CR-3): funding/OI/likidasyon backtest'te ancak gerçek zamanda erişilebilir olduğu anda (`available_at ≤ karar_anı`) kullanılabilir; saat sonu verisiyle saat başında işlem = look-ahead.
   - Maliyet: komisyon + kayma + funding her koşuda açık (`config/costs.yaml`); "maliyetsiz sonuç" raporlanmaz.
   - Karşılaştırma tabanı: buy&hold BTC ve basit EMA-kesişim kontrol stratejisi (S-0001). Kontrolü geçemeyen strateji tartışılmaz.
0. **Nabız kapısı (ADR-0006, 4 Ağu 2026):** Strateji kodu yazılmadan ÖNCE
   `scripts/signal_pulse.py` koşulur — çıkış kuralı, stop, maliyet ve boyutlandırma
   olmadan sinyalin ham forward getirisi taban dağılımla karşılaştırılır. Ölçülebilir
   öngörü gücü göstermeyen hipotez için strateji YAZILMAZ. Gerekçe: Kart A'da 3 strateji
   sürümü ve 17 backtest koşusu, tek bir ölçümle baştan elenebilecek bir sinyal için
   harcandı.

   **Yöntem v2 zorunluluğu (ADR-0007):** Her ufuk kendi forward-return null'una karşı
   circular moving-block bootstrap ile sınanır; örtüşen sinyaller efektif olay olarak
   tekilleştirilir; test alternatifi sonuç görülmeden tanımlanır; NaN/geçersiz test FDR
   evrenine girmez; seanslar DST-aware ve referans giriş sonraki mum açılışıdır.

   **Bağımsız İnceleme Kapısı v2 (ADR-0012):** `run_pulse_reanalysis.py` kapısı
   schema v2 formatında `pulse-v2-review.json` gerektirir. İnceleme kaydı `reviewed_commit`
   değerinin git geçmişinde mevcut HEAD'in atası olduğunu ve `review_scope` içindeki tüm
   dosyaların SHA-256 hash'lerinin korunduğunu doğrular. Onay kaydının ayrı commit
   edilmesi kapıyı kilitlemez (bootstrap paradoksu çözülmüştür); ancak kapsanan araştırma
   kodlarının sonradan değiştirilmesi onayı derhal geçersiz kılar.

4. **Aşırı-uyum (overfitting) korkulukları:** strateji başına ≤6 serbest parametre; hyperopt sonrası parametre hassasiyet testi (±%20 oynatınca sonuç çökmemeli); tarih aralığı seçerek sonuç güzelleştirme yasak.

   **Faz 2 istatistik kapıları (ADR-0019):** Yeni bir hipotez ailesi Development verdict'i
   almadan önce `phase2-statistical-gates/v1` raporu üretir. DSR deneme sayısı elle girilmez;
   Registry'deki yapılandırılmış, etkin ve benzersiz
   `(hypothesis_id, strategy_version, dataset_snapshot)` kanıt evreninden gelir. Effective
   `invalid` duplicate satırlar ve eski protokolde `result` gövdesi olmayan koşular bu evrene
   girmez. DSR getiri matrisi Registry evreniyle tam eşleşmezse değerlendirme durur.

   PBO/CSCV, config'deki çift partition sayısıyla konfigürasyon × zaman/fold net-getiri
   matrisini kombinatoryal train/test yarımlarında sınar; kombinasyon bütçesi aşılırsa örnekleme
   yapmaz, fail-loud durur. Hassasiyet planı her ön-kayıtlı pozitif sayısal parametreyi tek tek
   config'deki göreli delta kadar (varsayılan ±%20) oynatır ve hem `realistic` hem
   `taker_heavy` performans korunmasını ister. Ablation her veri ailesini aynı fold ve aynı
   maliyet senaryosunda çıkarıp tam modelle eşleşmiş karşılaştırır; eksik fold sıfır sayılamaz.
   CLI yalnız hazırlanmış JSON kanıtını okur/stdout raporu üretir, Registry'ye yazmaz ve
   Development sınırını aşan bundle'ı reddeder.

   **Dönem/venue kırılganlığı (ADR-0020):** Aynı adayın ön-kayıtlı en az üç Development
   dönemi ve en az iki bağımsız venue dilimindeki net getirileri ayrı tutulur. Her grubun
   iki maliyet senaryosu için asgari gözlem sayısı config'dedir. Kapı, gruplar arası ortalamaya
   göre en kötü grubun korunma oranını ve pozitif grup oranını ölçer; mutlak getiri eşiği
   kullanmaz. Eksik venue/dönem, kısa seri, NaN veya ortak ortalamanın pozitif olmaması
   dayanıklılık diye yorumlanamaz. Binance dışı gerçek venue verisi hazır değilken kapı
   sentetik test edilebilir, fakat gerçek bir hipoteze `passed` kanıtı üretemez.

   **F-0001 kırılganlık kalibrasyonu:** Ürün v1'in ilk aktif araştırması yön veya getiri
   üretmez. PIT-güvenli birleşik kırılganlığın kendi 90 günlük dağılımındaki üst göreli
   diliminin, sonraki 24 saatte gerçekleşen volatilite genişlemesi olay oranını artırıp
   artırmadığı sınanır. Olay eşiği yalnız settled geçmiş oranların göreli dağılımından gelir;
   örtüşen tetikler tekilleştirilir. Binance futures ve Coinbase spot sonuç serileri birlikte
   zorunludur. Eksik venue/örneklem `unavailable`dır; direction her koşulda null kalır.

   Hazırlanmış F-0001 olay satırlarının değerlendirmesi `scripts/fragility_calibration.py`
   ile yapılır. Olasılıklar yalnız train fold'dan öğrenilir; event-rate lift, equal-coverage
   recall lift, Brier skill ve pozitif fold oranı yalnız pooled test tahminlerinden gelir.
   İki venue ayrı kapılardır. Bu çekirdek OHLCV'den tetik/etiket üretmez ve provenance'sız
   hazırlanmış satır gerçek verdict için kullanılamaz.

   `scripts/fragility_event_rows.py`, bu hazırlanmış satırları üretir: direction-null exact-hour
   context'ten rolling göreli tetik, kesintisiz saatlik venue OHLCV'den yalnız settled geçmişe
   dayalı +24h genişleme etiketi çıkarır. Cooldown içi saatler false baseline'a dönüştürülmez.
   İki venue, config ve tüm input gövdeleri artefakt hash'ine bağlanır.

**Maliyet konfigürasyonu (CR-5):** Tüm maliyet parametreleri `config/costs.yaml`'dadır — komisyon (taker 0.00045 VIP0+BNB, muhafazakâr alternatif 0.0005; maker 0.00018), tek yön kayma (BTCUSDT 0.0002, ETHUSDT 0.00025), funding (`mode: historical` — freqtrade futures modunda tarihsel funding serisi indirilir ve kullanılır; fallback düz 8s 0.0001) ve 5 kademeli stres senaryosu matrisi (optimistic_maker 2 bps → cascade 60 bps; cascade satırı PARK stratejileri açılırsa fill-olasılığı modeliyle zorunlu). Not: funding borsaya ödenmez, taraflar arası transferdir; long-bias stratejide pozitif funding dönemleri maliyet, short-bias'ta gelir olarak tarihsel seriden doğal biçimde gelir. Her backtest koşusu senaryo adını raporuna yazar.
5. **Kabul/ret kaydı:** sonuç ne olursa olsun `docs/hypotheses/NNNN.md` güncellenir — reddedilen hipotez de kayıttır (yayın yanlılığını kendi içimizde engelliyoruz).
6. **Dry-run karantinası:** backtest'i geçen strateji ≥4 hafta dry-run'da izlenir; canlı sinyal kalitesi backtest'ten anlamlı sapıyorsa geri alınır.

### 3.1 İlk strateji seti (CR-4 ile yeniden tanımlandı; S-0004 ayrımı CR-002 P0-7)
| Kod | Hipotez (kaynak kart) | Öncelik | Not |
|---|---|---|---|
| S-0001 | EMA(20/50) kesişimi + ATR stop | Taban | Kontrol/taban çizgisi — iyi olduğu için değil, kıyas için |
| ~~S-0002~~ | ~~Hacim-koşullu intraday momentum (Kart A)~~ | **KAPALI / KANIT DÜZELTİLDİ** | Kaynak ayrılmıyor; ham büyüklükler negatif/düşük. S-0002 ve S-0002b koşuları INVALID; eski p-değerleri ve “tam sadakat” iddiası ADR-0007 ile geri çekildi. |
| S-0003 | **Rejim filtresi = funding–OI–likidasyon (Kart E+G+L), meta-labeling** | 2 | Yön üretmez; S-0002+ sinyallerine izin/boyut verir. btc-radar Faz D entegrasyonunun hedefi. Önce GÖZLEM modunda (bloklamaz, loglar — CR-002 yol haritası 7) |
| S-0004a | **Seans volatilite kırılması (Kart I)** | 3 | Neredeyse günlük örneklem; seans tanımı Kart I kurallarıyla (TZ-aware) |
| S-0005 | **FOMC event-study (Kart K)** | 4 | Seyrek olay, ayrı pipeline; karartma penceresinde "armed" bekler (P0-7) |
| PARK | Jump-reversal (B/H) | — | Maliyet hassasiyeti "çok yüksek" + tek-olay kanıtı; stres-slippage altyapısı (CR-5) oturmadan test edilmez |
| PARK | Mum sınırı (D) | — | 1m/tick veri gerektirir + bozunmaya en açık aday |
| RET | Delta-neutral basis arb (F) | — | Ürün kapsamı dışı (iki bacak, borç, sermaye operasyonu) |
| HAVUZ | N, O, P, Q | — | Düşük kanıt; hipotez havuzunda kanıt etiketiyle bekler, kör test edilmez |

A–Q kartlarının her biri `docs/hypotheses/` altına kanıt düzeyi + kaynak + zayıflık alanlarıyla birer dosya olarak işlenir (kaynak: `docs/research/hipotez-arastirmasi.md`).

---

## 4. Sinyal Bildirim Sözleşmesi

Teslimat süreci servis kökündeki `.env` dosyasını yükler; process environment değerleri
dosya tarafından ezilmez. `RADAR_SIGNAL_DELIVERY_MODE` zorunludur ve yalnız `telegram` veya
`console` olabilir. `telegram` modunda bot token ile chat id birlikte yoksa süreç outbox'ı
pompalamadan fail-closed durur; eksik secret hiçbir zaman console teslimatına dönüşmez.
`console` yalnız açık yerel geliştirme seçimidir. Secret değerleri repoya, config'e veya hata
mesajına yazılmaz.

Her Telegram mesajı şu alanları içerir (webhook enricher üretir):
```
[SİNYAL] ETHUSDT LONG · 15m · 2026-08-03 14:32 UTC
Strateji: S-0002 (trend-pullback) · etiket: rsi_bounce_uptrend
Gerekçe: 1h EMA50 üstünde; 15m RSI 34→41 dönüş; hacim 20-bar ort. üstü
Rejim (radar): yön +31, kırılganlık 44, güven 78 [Faz D'den itibaren]
Referans: giriş bölgesi X, invalidasyon Y (ATR tabanlı), hedef bölge Z
Not: Araştırma sinyalidir; yatırım tavsiyesi değildir. Karar ve risk kullanıcıya aittir.
```
Kural: fiyat seviyeleri "bölge/referans" dilinde verilir, emir talimatı dilinde verilmez. Kırılganlık ≥60 iken sinyal mesajına otomatik uyarı satırı eklenir; güven <55 iken rejim satırı "veri yetersiz" der (btc-radar fail-closed ilkesi buraya taşınır).

---

## 5. AI Orkestrasyonu (bu projede)

| Rol | Araç | İş |
|---|---|---|
| Tek yazar | Claude Code | Strateji sınıfları, enricher servisi, test/CI, hipotez kartları |
| Backtest analisti | Claude Code (+ Gemini büyük CSV'lerde) | Koşu sonuçlarını okuma, pencere bazlı zayıflık tespiti |
| İncelemeci | Cursor/Codex | Strateji PR'larında look-ahead bias, veri sızıntısı, off-by-one avı |
| Rejim beyni | btc-radar MCP + skill | Faz D: sinyal filtreleme bağlamı; günlük rejim raporu |
| Canlı döngü | — | LLM YOK. Deterministik kod. |

**Look-ahead bias avı incelemenin 1 numaralı maddesidir:** intraday stratejilerde en sık hata, kapanmamış mum verisini veya geleceği gören shift hatasını kullanmaktır. Her strateji PR'ında incelemeciye açıkça bu sorulur.

**Raporlama kütüphanesi (CR-7):** Faz C/E performans raporlarında **quantstats** kullanılır, pyfolio KULLANILMAZ (pyfolio/empyrical 2020'den beri bakımsız — RESEARCH-RADAR v1.1). freqtrade'in quantstats entegrasyonundan yararlanılır.

---

## 5.1 Rejim Matrisi — S-0003 Tasarım Referansı (CR-8)

Hipotez araştırmasındaki volatilite × funding/OI × likidasyon çerçevesi (kaynak: `docs/research/hipotez-arastirmasi.md`, "Rejim matrisi" bölümü). **Bu matris config değil tasarım dokümanıdır**; kurallara dönüşümü S-0003 hipotez kartında yapılır.

| Volatilite | Funding/OI | Likidasyon | Tercih edilecek hipotez |
|---|---|---|---|
| Düşük | Nötr | Düşük | Range mean reversion |
| Yükseliyor | Nötr | Düşük | Hacim teyitli breakout |
| Yüksek | OI yükseliyor | Düşük | Momentum; fakat kırılganlık artıyor |
| Yüksek | Funding aşırı | OI aşırı | Yeni giriş azalt; failure/reversal izle |
| Çok yüksek | OI sert düşüyor | Çok yüksek | Kaskad devamı, sonra exhaustion |
| FOMC/expiry penceresi | Herhangi | Herhangi | Olay modeli veya no-trade |
| Hafta sonu | Herhangi | Düşük | Daha sıkı likidite ve cross-venue teyidi |

Araştırmanın ana bulgusu tasarımı doğrular: funding/OI/seans verileri yön sinyali değil **rejim filtresidir**; en kalıcı etkiler yön değil volatilite zamanlamasıdır.

---

## 6. Yol Haritası

**Sıralama otoritesi CR-002 "Yol haritası yeniden sıralaması"dır** (Değ-1 önerisi kabul): 1) S-0001 ayakta · 2) sinyal→snapshot→ledger→Telegram yaşam döngüsü uçtan uca · 3) replay testi · 4) gerçekçi giriş/çıkış simülatörü · 5) Experiment Registry · 6) S-0002 · 7) rejim filtresi önce gözlem modunda · 8) yeterli örnekle çıplak/+rejim kıyası · 9) S-0004a seans · 10) S-0005 FOMC ayrı pipeline · 11) jump-reversal tick verisi olmadan asla.

| Faz | İçerik (CR-002 sırasıyla) | Bitti kriteri |
|---|---|---|
| **A — Kurulum + kanıt zinciri** (adım 1-5) | freqtrade + veri (bütünlük manifestli) + costs.yaml + Registry v0 + S-0001 + yaşam döngüsü uçtan uca (state machine, outbox, Telegram) + replay determinizmi + muhafazakâr simülatör + Registry tam şema | S-0001 maliyet dahil koşuyor; 100 replay bit-bit özdeş; 10dk Telegram kesintisi kayıpsız |
| **B — Fabrika** (adım 6) | Walk-forward otomasyonu, hipotez kartı şablonu, S-0002 protokol koşusu | S-0002 protokolün tamamından geçti (kabul veya gerekçeli ret) |
| **C — Karantina** (adım 7-8) | Dry-run izleme; rejim filtresi GÖZLEM modunda; çıplak/+rejim kıyası | 4 hafta kesintisiz dry-run verisi ve sapma raporu |
| **D — Rejim entegrasyonu** (adım 7+) | btc-radar HTTP; enricher rejim satırı canlı; S-0003 meta-labeling | Kırılganlık filtresi A/B olarak backtest'lendi |
| **E — Değerlendirme** (adım 9-10 dahil) | S-0004a/S-0005; 3 aylık dry-run verisiyle karar | Veriye dayalı yazılı değerlendirme raporu |

---

## 7. Riskler

| # | Risk | Karşılık |
|---|---|---|
| 1 | Intraday'de maliyet avantajı yutar | Başarı tanımı maliyet-sonrası; kontrol stratejisi kıyası zorunlu |
| 2 | Overfitting (en olası başarısızlık nedeni) | §3.4 korkulukları + out-of-sample kilidi + ret kayıtları |
| 3 | Sinyal gecikmesi (insan okuma süresi) | 15m/1h seçimi bu yüzden; mum kapanışında sinyal, "bölge" dili |
| 4 | Kullanıcının sinyale aşırı güveni | Her mesajda invalidasyon + yasal not; haftalık "sinyal karnesi" raporu (isabet/ıska şeffaflığı) |
| 5 | Binance veri/erişim değişiklikleri | ccxt soyutlaması; Bybit yedek borsa olarak config'de hazır |
| 6 | Strateji sayısı şişer, bakım çöker | Aynı anda yayında ≤3 strateji; yenisi girerken en zayıfı karantinaya döner |
