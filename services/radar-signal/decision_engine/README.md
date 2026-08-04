# BTC 1h Paper Decision Engine

Bu paket, kapanmış BTCUSDT 1h mumunu sürümlü bir teknik feature snapshot'a dönüştürür ve
her değerlendirilen saat için deterministik `LONG`, `SHORT` veya `WAIT` karar kartı üretir.
Gerçek emir göndermez; scheduler, provider ve strateji içermez.

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
