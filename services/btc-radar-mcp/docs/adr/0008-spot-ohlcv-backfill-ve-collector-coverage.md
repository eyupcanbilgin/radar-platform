# ADR 0008 — Spot OHLCV backfill ve yeni collector coverage kanıtı

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0005, ADR-0006, ADR-0007, Hedefe Geliştirme Planı Faz 1

## Bağlam

ADR-0007 spot OHLCV, spot/perp basis ve order-book spread/depth verisini canlı PIT akışına
ekledi. Ancak spot serisinin geçmişi yoktu ve `collection_coverage` yalnız feature config'ine
bağlı funding/OI metriklerini gösteriyordu. Bu durum iki ayrı soruyu görünmez bırakıyordu:
spot mum geçmişi tamam mı ve yeni canlı collector'lar gerçekten kesintisiz çalışıyor mu?

Üç aile aynı geçmiş imkânına sahip değildir. Binance spot `klines` ucu `startTime/endTime`
ile geçmiş kapanmış mumları verir. Spot ticker, perpetual mark ve depth uçları ise yalnız
istek anındaki durumu verir; tarihsel basis veya order-book snapshot sağlamaz.

## Kararlar

1. `BinanceSpotHistoryProvider`, canlı provider'dan ayrı adla yalnız `ohlcv_1h` geçmişi
   okur. `startTime` ile ileri, en fazla 1000 mumluk sayfalar kullanılır; dönen sıra artan
   değilse veya satır şeması değişmişse fail-loud davranır.
2. Açık mum kullanılmaz. Satırın `closeTime` değeri hem retrieval anından hem istenen
   `end_time` sınırından küçük/eşit olmalıdır.
3. Backfill satırı `available_at = closeTime + publication_lag` taşır. `provider` adı ve PIT
   `ingested_at`, geçmişin sonradan yeniden kurulduğunu canlı uptime kanıtından ayırır.
4. `backfill --spot-days` funding/OI ile aynı bounded CLI akışına eklenir. Sonuç kaç mum
   istendiğini değil gerçekte kaç OHLCV gözlemi yazıldığını, kapsanan olay zamanını, en büyük
   boşluğu ve `max_pages` kırpmasını raporlar.
5. `signal_rules.yaml` içinde scoring feature'larından ayrı `collection_metrics` bölümü
   açılır. Spot close saatlik; basis ve order-book spread scheduler'ın 300 saniyelik canlı
   cadence'iyle izlenir. Bu kayıtlar feature değildir, skor veya yön üretmez.
6. Coverage her metriğe `history_mode` ekler. Spot close `backfill_and_live`; basis ve depth
   `live_only` olarak açıkça etiketlenir. OHLCV'den basis/depth tahmin etmek veya geçmiş boşluğu
   nötr değerle doldurmak yasaktır.
7. Depth ailesinde `order_book_spread_bps` temsilci metriktir. Spread ve iki depth değeri aynı
   tek endpoint yanıtından, aynı event/availability anında atomik PIT append içinde gelir;
   üç aynı coverage satırı üretmek yeni kanıt sağlamadan raporu şişirirdi.
8. Taze tek örnek bütün pencereyi sağlıklı göstermez. `healthy` artık beklenen örnek sayısının
   tamamı (`complete`) yanında boşluk ve tazelik şartlarını birlikte ister.

## Sonuçlar ve sınırlar

Canlı doğrulama (5 Ağustos 2026): 1 günlük istek 23 tam kapanmış mumdan 115 OHLCV gözlemi
yazdı; en büyük boşluk 3600 saniyeydi ve availability her satırda kapanış + 60 saniyeydi.

`status` ve `get_health`, funding/OI yanında spot close, basis ve order-book collector
boşluklarını da gösterir. Backfill edilmiş spot seri piyasa geçmişi kanıtıdır; o saatte
producer'ın ayakta olduğunun kanıtı değildir. Basis/depth için yalnız canlı birikim vardır.

Bu ADR yeni fragility feature'ı, rejim veya direction açmaz. `direction` her koşulda null
kalır. Alarm/Telegram operasyon bildirimi Faz 3 işidir.
