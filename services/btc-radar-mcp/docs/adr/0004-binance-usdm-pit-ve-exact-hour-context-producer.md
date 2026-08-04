# ADR 0004 — Binance USD-M provider, PIT toplama ve exact-hour context producer

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0003, Signal ADR-0009, `decision-context/v1`

## Bağlam

MCP iskeleti, PIT deposu ve snapshot aritmetiği vardı; fakat gerçek provider ve signal
inbox'ına yayın yapan producer yoktu. `signal_rules.yaml` hâlâ boştur. Bu durumda gerçek
Binance değerlerinden yön/kırılganlık üretmek bilimsel olarak savunulamaz: test builder'ı
ham değeri kullanmayan sabit test kurallarıdır ve üretim kuralı değildir.

Saat kapanışından sonra çekilmiş anlık bir değeri kapanış anında biliniyormuş gibi geriye
tarihlemek de look-ahead olur. Producer'ın ilk görevi skor üretmek değil, bu zaman sınırını
bozmadan gerçek gözlemi saklamak ve signal servisine dürüst bir veri kapısı taşımaktır.

## Karar

1. `BinanceFuturesProvider` yalnız anahtarsız public BTCUSDT USD-M verisi okur:
   `/fapi/v1/premiumIndex` → `mark_price` + `funding_rate`,
   `/fapi/v1/openInterest` → `open_interest`. Private endpoint, API key ve emir yüzeyi yoktur.
2. Her gözlemde `available_at = max(retrieved_at, exchange_event_time)` kullanılır. Böylece
   yerel saat biraz geride olsa bile gelecek zamanlı veri görünmez; kapanıştan sonra alınan
   örnek aynı kapanış snapshot'ına giremez. Historical OI/funding ayrı availability
   semantiği gerektirdiğinden bu provider'a karıştırılmaz.
3. Ağ çağrıları en fazla üç denemelidir. Timeout/transport, 408, 429 ve seçili 5xx yanıtları
   sınırlı beklemeyle yeniden denenir; parse/şema hataları, 418 ve kalıcı 4xx fail-loud'dur.
   Testler kaydedilmiş gerçek response fixture'larıyla çalışır; pytest canlı ağa çıkmaz.
4. Yalnız tam aynı bilgi-zamanı satırı idempotenttir. Farklı `available_at` sistemin bilgi
   zaman çizelgesinde ayrı kanıttır ve append-only saklanır. Böylece geç gelen erken kayıt ve
   A→B→A revizyonu kaybolmaz; collector yazma sırası geçmişi değiştirmez.
5. `produce_unscored_context`, exact-hour PIT satırlarını snapshot `input_digest`'ine alır
   fakat boş component kümesi kullanır. Çıktı zorunlu olarak `direction=null`,
   `fragility=null`, `confidence=0`, `regime_label=veri_yetersiz` ve
   `scoring_rules_unavailable` blocker'lıdır. `signal_rules.yaml` dolarsa gerçek builder
   bağlanana kadar producer çalışmayı reddeder.
6. Snapshot bütünlüğü yazmada ve okumada yeniden doğrulanır: `data_cutoff_at == as_of`,
   türetilmiş `snapshot_id`, içerik hash'i, sıralı/tekil kalite listeleri ve sonlu breakdown
   sayıları. Producer context ayrıca exact UTC saat zorlar. Feature snapshot sürümü `0.2.0` olur ve
   `data_cutoff_at` artık içerik hash'ine dahildir. Eski `0.1.0` kayıtları kendi legacy hash
   sözleşmesiyle doğrulanmaya devam eder. Exact-hour kuralı genel SnapshotStore'a değil context
   publisher'a aittir. Aynı `as_of` için birden fazla snapshot varsa `get_as_of` duvar saatine
   göre örtük “latest” seçmez. Eşzamanlı producer yazımları `BEGIN IMMEDIATE` transaction ile
   serialize edilir; biri oluşturur, diğerleri doğrulayıp idempotent döner.
7. Context yayını aynı dizinde temp dosya + flush + `fsync` + `os.link(temp, final)` kullanır.
   Hard-link final yolu atomik görünür yapar ve mevcut hedefi Windows/POSIX'te overwrite
   etmez. Hard-link kullanılamıyorsa güvensiz `os.replace` fallback'i yapılmaz. Yalnız
   `computed_at_utc` farkı semantik idempotent sayılır; başka fark conflict'tir. Bozuk mevcut
   artifact asla üzerine yazılmaz.
8. Toplama ve yayın ayrı CLI komutlarıdır. Collector saat boyunca ayrı cadence ile çalışmalı,
   publisher kapanıştan sonra çağrılmalıdır. Bu ADR scheduler/process supervision eklemez.
   `get_derivatives` MCP aracı aynı provider'ın normalize anlık gözlemlerini sunar ve skorlama
   durumunu açıkça unavailable bildirir.

## Sonuçlar ve sınırlar

Gerçek Binance → PIT → değişmez snapshot → exact-hour JSON → signal consumer taşıması artık
çalışır ve fail-closed'dur. Buna karşın tarihsel feature'lar, rolling percentile/z-score,
gerçek fragility builder, direction kuralları, çok-kaynak kapsamı, cache/router, scheduler,
alarm ve kesintisiz işletim kanıtı henüz yoktur. Bu paket “veri taşıması hazır” demektir;
“rejim analizi hazır” veya “para kazandıran sinyal hazır” demek değildir.
