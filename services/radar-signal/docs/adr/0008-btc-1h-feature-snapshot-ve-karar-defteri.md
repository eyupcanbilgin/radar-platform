# ADR-0008 — BTC 1h FeatureSnapshot ve append-only karar defteri

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0003, `decision-context/v1`, Hedefe Geliştirme Planı Faz 1

## Bağlam

Mevcut `SignalLedger`, yalnız oluşmuş LONG/SHORT webhook sinyallerinin mutable yaşam
döngüsünü tutuyor. Setup olmayan saatleri kaydetmiyor ve `WAIT` ölçülemiyor. Ayrıca teknik
feature girdileri sürümlü/değişmez bir artefakt olarak saklanmadığından aynı kararın neden
üretildiği bağımsız replay edilemiyordu.

Bu aşamada kabul edilmiş yönsel strateji ve gerçek MCP provider'ı yoktur. Buna rağmen ürün
döngüsünün `no-trade` davranışı, zaman/hashing kuralları ve defteri veri gelmeden güvenli
biçimde kurulabilir.

## Karar

1. `SignalLedger` değiştirilmez. Önüne ayrı `decision_engine` ve `DecisionLedger` konur.
2. `FeatureSnapshotV1`, yalnız kapanmış ve `available_at <= as_of` olan BTCUSDT 1h
   mumlarından üretilir. Sabit lookback 200 bardır; eksik/gap durumunda snapshot üretilir
   fakat `ready=false` olur.
3. Feature seti `btc-1h-core-v1` olarak sürümlenir: close, 1h return, 24h RMS log-return
   volatility, önceki 24 saate göre volume ratio, EMA20/EMA50 mesafesi ve ATR14-SMA yüzdesi.
4. Feature kimliği semantik girdilerden; content hash türetilmiş çıktıların tamamından
   türetilir. Aynı girdi+sürüm farklı çıktı üretirse aynı kimlik/farklı hash çatışmasıdır.
5. Karar sırası `feature_ready -> context_gate -> candidate_present` olur. Context yok,
   zorunlu veri kapalı veya setup yoksa saat atlanmaz; açık blocker/gerekçeyle `WAIT` olur.
   MCP direction skoru yön sinyali sayılmaz. Her yönsel setup tam karar saati ile feature
   snapshot ID/hash'ine bağlıdır; başka saatten veya feature artefaktından taşınamaz.
6. `DEC-*` doğal saat slotundan türetilir; sonuçtan türetilmez. Aynı saatin farklı kod,
   policy, feature, context veya sonuçla yeniden yazılması yasaktır.
7. Feature ve karar tek `BEGIN IMMEDIATE` transaction'ında iki tabloya eklenir. Foreign key
   açıktır; UPDATE/DELETE ve çakışan INSERT/REPLACE SQLite trigger'larıyla reddedilir. Tam
   aynı retry idempotenttir.
8. Ledger tam feature/context/decision payload'ını, policy hash'ini ve signal commit SHA'sını
   saklar. `recorded_at_utc` audit metasıdır, semantik kimliğe girmez.
9. Ledger, gelen kartı girdilerden deterministik olarak yeniden üretmeden kaydetmez. Okumada
   hash/link denetimine ek olarak indeks kolonları ile değişmez payload tutarlılığını doğrular.

## Bilinçli kapsam dışı

- Saatlik scheduler ve gerçek mum/context taşıması
- Yönsel setup/strateji kuralları
- Telegram teslimi ve eski SignalLedger/outbox crash-gap onarımı
- Karar outcome evaluator (ayrı append-only olay/tablo olacaktır)

## Sonuçlar

Setup üretmeyen mevcut sistem artık bir saat işlendiğinde dürüst ve ölçülebilir `WAIT`
üretebilir. Ancak scheduler bağlanmadığı için “kesintisiz her saat çalışıyor” iddiası henüz
yapılamaz. LONG/SHORT arayüzde mümkündür fakat yalnız ileride hipotez kartlı bir setup
motorundan gelebilir.
