# BTC 1h Paper MVP Kapsamı

## Sabit ürün dilimi

İlk çalışan dikey dilim yalnız şudur:

`BTCUSDT · Binance USDT perpetual · 1h kapanmış mum · LONG/SHORT/WAIT · paper`

Bu kapsamda gerçek emir, private borsa endpoint'i, ETH, 15m karar döngüsü, haber/LLM kararı,
portföy optimizasyonu ve kullanıcıya pozisyon talimatı yoktur.

## Saatlik karar akışı

1. Kapanmış 1h mumun `as_of` anı belirlenir.
2. MCP/PIT katmanı yalnız `available_at <= as_of` gözlemlerinden rejim snapshot'ı üretir.
3. Snapshot, `decision-context/v1` sözleşmesiyle signal servisine aktarılır.
4. Signal servisi teknik setup'ı ve veri/risk kapılarını deterministik değerlendirir.
5. Sonuç mutlaka `LONG`, `SHORT` veya `WAIT` olur. Setup yokluğu ve blocker'lar açıkça yazılır.
6. Karar; snapshot, sürüm, gerekçe ve veri sağlığıyla decision ledger'a eklenir.
7. Referans sonuçlar +1h/+4h/+24h, MFE/MAE ve maliyetlerle sonradan ölçülür.

## Fail-closed sınırı

Zorunlu bir kaynak/katman eksik veya bayatsa `directional_decision_allowed=false` olur ve
tek izinli ürün çıktısı `WAIT`tir. Opsiyonel kapsam eksikliği görünür `degraded` uyarısıdır;
hangi girdilerin zorunlu olduğu config ile sürümlenir.

MCP bağlam sağlar; tek başına `LONG` veya `SHORT` üretmez. LLM canlı döngüde yer almaz.
