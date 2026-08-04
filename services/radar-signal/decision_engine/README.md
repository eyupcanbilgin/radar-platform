# BTC 1h Paper Decision Engine

Bu paket, kapanmış BTCUSDT 1h mumunu sürümlü bir teknik feature snapshot'a dönüştürür ve
her değerlendirilen saat için deterministik `LONG`, `SHORT` veya `WAIT` karar kartı üretir.
Gerçek emir göndermez. Public Binance mum adaptörü ve UTC scheduler içerir. MCP tarafında
exact-hour context producer vardır; fakat producer henüz unscored/fail-closed'dur ve kendi
scheduler'ı yoktur. Kabul edilmiş yönsel strateji de henüz yoktur.

## FeatureSnapshot v1

Yalnız `close_time <= as_of` ve `available_at <= as_of` mumları görülebilir. Son 200 saat
kesintisiz değilse snapshot yine üretilir fakat `ready=false` olur ve karar `WAIT`e kapanır.

Sürümlü feature seti `btc-1h-core-v1`:

- kapanış fiyatı;
- son 1h basit getiri;
- son 24 log getirinin yıllıklandırılmamış RMS volatilitesi;
- son mum hacmi / önceki 24 mum ortalama hacmi;
- EMA20 ve EMA50'ye yüzde uzaklık (200 bar warm-up);
- son 14 true range'in basit ortalaması / kapanış yüzdesi.

`FS-*` kimliği yalnız instrument, `as_of`, input digest ve feature sürümünden türetilir.
Türetilmiş değerler `content_hash` içindedir. Böylece aynı girdi+sürüm farklı çıktı üretirse
kimlik sabit, hash farklı kalır ve ledger sürümsüz kod değişikliğini reddeder.

## Saatlik karar

Kapılar sırayla feature readiness, decision-context veri kapısı ve yönsel setup varlığıdır.
İlk kapalı kapı yönsel kullanımı engeller; saat atlanmaz ve açık gerekçeli `WAIT` kaydedilir.
Context tamamen yoksa `context:missing`, setup yoksa `no_directional_setup` yazılır. MCP'nin
pozitif/negatif direction skoru tek başına yönsel karara çevrilmez. Yönsel setup, başka bir
saatten veya feature üretiminden taşınamasın diye tam `as_of + feature snapshot ID/hash`
bağını taşır ve karar kurulmadan önce doğrulanır.

`DEC-*` kimliği doğal saat slotundan (`instrument + as_of + paper`) türetilir. Sonucun,
context'in, feature'ın, policy/code sürümünün değişmesi kimliği değiştirmez; içerik hash'ini
değiştirir ve aynı saat yeniden yazılamaz.

## DecisionLedger

Tek SQLite transaction'ı feature snapshot ile karar kartını birlikte ekler. İki tablo da
UPDATE/DELETE ve çakışan INSERT/REPLACE trigger'larıyla append-only'dir. Tam aynı retry
idempotenttir; aynı saat farklı artefaktla gelirse `ImmutableDecisionError` oluşur. Ledger,
kartı kaydetmeden önce feature/context/setup girdilerinden yeniden üretir. Feature, context ve
karar payload'ları replay için saklanır; okumada hash/link ve kolon-payload tutarlılığı yeniden
doğrulanır.

Karar sonuçları bu satırlara sonradan yazılmayacaktır; outcome evaluator ayrı append-only
event/tablo kullanacaktır.

## Saatlik runtime

Runtime public ve anahtarsız `ccxt.binanceusdm` üzerinden yalnız
`BTC/USDT:USDT · contract-price · 1h` mumlarını okur. Tam 200 saatlik pencere sunucu tarafında
`until=as_of-1ms` ile kapanır; açık mum ayrıca consumer tarafında elenir. HTTP gözlem zamanı
audit çıktısında tutulur, feature kimliğine girmez. Varsayılan karar gecikmesi 90 saniyedir ve
ağ retry bütçesi 3 denemedir. Slot uygunluğu yerel saate değil Binance `serverTime` değerine
göre belirlenir; borsa saati doğrulanamazsa o saat için erken ve değişmez kayıt yazılmaz.

Context yalnız şu exact-hour yoldan okunur:

```text
var/decision-context/v1/BTCUSDT/1h/YYYY/MM/DD/HH.json
```

Önceki/en yeni saate fallback yoktur. Dosya yoksa veya sözleşme doğrulamasından geçmezse
runtime bunu görünür kaynak durumuyla raporlar ve karar `WAIT/context:missing` olur. MCP
producer aynı dizinde tamamlanmış temp dosya + `fsync` + atomik no-overwrite hard-link ile
yayın yapar; mevcut saat dosyasını asla değiştirmez. Bugünkü unscored context geldiğinde
dosya `ready` okunur ama veri kapısı `scoring_rules_unavailable` nedeniyle `WAIT`e kapanır.

Tek-sefer çalıştırma:

```powershell
.venv\Scripts\python.exe scripts\run_hourly_decision.py
```

UTC daemon:

```powershell
.venv\Scripts\python.exe scripts\run_hourly_decision.py --daemon
```

Açık tarihsel saat yalnız replay/backfill'dir ve varsayılan olarak production defteri yerine
`var/hourly-replay.sqlite` kullanır:

```powershell
.venv\Scripts\python.exe scripts\run_hourly_decision.py `
  --as-of 2026-08-04T12:00:00Z
```

Runtime başlangıçta temiz signal worktree ve 12 karakterlik commit provenance ister. Git
checkout içindeki açık commit değeri mevcut signal commit'iyle aynı olmalıdır; override yalnız
Git metadatası bulunmayan paketli ortam içindir. Aynı DB için tek daemon çalıştırılmalıdır.
Process supervision, heartbeat/alarm ve uzun süreli çalışma kanıtı henüz ayrı iş paketidir.
