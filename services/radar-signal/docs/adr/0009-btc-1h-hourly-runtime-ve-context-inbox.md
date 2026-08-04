# ADR-0009 — BTC 1h saatlik runtime ve exact-hour context inbox

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0003, Signal ADR-0008, `decision-context/v1`

## Bağlam

ADR-0008 deterministik feature/karar çekirdeğini ve değişmez karar defterini kurdu; gerçek
mum taşıması, context taşıması ve scheduler bilinçli olarak dışarıda kaldı. Freqtrade
strateji/backtest hattı CCXT üzerinden mum çekiyor. İlk BTC 1h karar defterinin ise kabul
edilmiş stratejisi ve çalışan bir Freqtrade sinyal kaynağı henüz yok.

MCP tarafında da somut provider, çalışan context endpoint'i veya HTTP transport yoktur.
Yalnız `stdio` health aracı ve test edilebilir PIT/snapshot çekirdeği vardır. Bu aşamada
doğrudan MCP SQLite şemasına bağlanmak veya var olmayan bir HTTP servisini taklit etmek servis
sınırını bozar ve gerçeğe aykırı bir entegrasyon görüntüsü yaratır.

## Karar

1. Standalone BTC 1h paper runtime, mevcut sabitlenmiş CCXT bağımlılığı üzerinden doğrudan
   `binanceusdm · BTC/USDT:USDT · 1h · contract-price` public OHLCV okur. API anahtarı,
   private endpoint ve emir yüzeyi yoktur. Bu adaptör MCP provider'ı değildir; Freqtrade
   strateji hattından bağımsız karar-defteri diliminin aynı veri sorumluluğundaki taşıyıcısıdır.
2. İstek tam karar penceresidir: `since=as_of-200h`, `limit=200`, `until=as_of-1ms`.
   Dönen her mumda kapanış `open+1h` olarak türetilir; açık/geçer-dışı mumlar kullanılmaz,
   gap doldurulmaz. Mantıksal `available_at` mum kapanışıdır; gerçek HTTP alınma zamanı ayrı
   batch audit metasıdır ve feature kimliğine girmez.
3. Ağ için en fazla üç deneme ve kısa sabit bütçe vardır. Rate-limit, DDoS koruması, kalıcı
   exchange hatası veya bozuk payload hızlı retry edilmez. Bütçe tükenirse saat atlanmaz;
   eksik feature gerekçeli, değişmez `WAIT` kaydı üretilir.
4. Runtime yeni slotu Binance `serverTime` UTC saat sınırından varsayılan 90 saniye sonra
   işler. Yerel makine saati slot uygunluğunun otoritesi değildir. Server time alınamaz veya
   grace sınırına ulaşmamışsa henüz doğrulanmamış slot için ledger satırı dondurulmaz. Yerel
   saat veya `schedule` tabanlı takvim kullanılmaz. Aynı slot defterde varsa kaynaklara
   yeniden gidilmez. Otomatik tarihsel catch-up yoktur.
5. Context taşıması exact-hour, sürümlü JSON inbox'tır:
   `var/decision-context/v1/BTCUSDT/1h/YYYY/MM/DD/HH.json`. Consumer yalnız tam yolu okur;
   “latest”, önceki saat, test fixture'ı veya başka snapshot fallback'i yapmaz. Yok/bozuk,
   yanlış saatli ya da future-cutoff context geçersizdir ve `WAIT/context:missing`e kapanır.
6. Inbox yerel-güvenilir taşıma sınırıdır. Gelecekteki MCP producer aynı filesystem'de geçici
   dosya + atomik rename ile yayınlamalı, mevcut saat dosyasını overwrite etmemeli ve kendi
   snapshot hash'ini yayın öncesi doğrulamalıdır. Signal consumer MCP iç DB'sini doğrudan
   okumaz ve MCP Python modüllerini import etmez.
7. `scripts/run_hourly_decision.py` varsayılan tek-sefer, açık `--daemon` ile sürekli UTC
   modudur. Açık `--as-of` yalnız replay/backfill sayılır ve özel ledger verilmezse ayrı
   `hourly-replay.sqlite` dosyasına yazar; canlı paper geçmişi gibi sunulmaz.
   Git checkout varsa worktree temiz olmalı; açık `--signal-commit` checkout commit'iyle
   eşleşmelidir. Bu argüman yalnız `.git` bulunmayan paketli ortamda provenance kaynağı olabilir.
8. Runtime yönsel setup kabul etmez. Kabul edilmiş setup motoru eklenene kadar mum ve context
   sağlıklı olsa bile dürüst sonuç `WAIT/no_directional_setup`tır. Gerçek emir her durumda
   kapalıdır.

## Sonuçlar

Karar çekirdeği artık gerçek public mumlarla tek-sefer veya saatlik daemon olarak
çalıştırılabilir ve restart sonrası aynı slotu yeniden fetch etmez. Ancak MCP context producer,
yönsel setup, process supervision, alarm/heartbeat ve kesintisiz işletim kanıtı hâlâ yoktur.
Dolayısıyla bu karar “çalışan sinyal botu” değil, canlı verili değişmez paper karar defteri
runtime'ı sağlar.
