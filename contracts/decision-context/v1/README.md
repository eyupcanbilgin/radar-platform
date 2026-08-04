# Decision Context v1

`decision-context/v1`, `btc-radar-mcp` tarafından üretilen değişmez rejim snapshot'ını
`radar-signal` karar döngüsüne taşır. Sözleşme yönsel setup üretmez ve hiçbir zaman emir
talimatı değildir.

## Kapsam

- Varlık: `BTC`
- Sembol: `BTCUSDT`
- Piyasa: Binance USDT perpetual
- Karar zaman dilimi: `1h`
- Çıktı kümesi: `LONG | SHORT | WAIT`
- Çalışma modu: yalnız `paper`

MCP'nin rolü rejim, kırılganlık, güven ve veri sağlığı bağlamı sağlamaktır. Teknik setup ve
nihai `LONG/SHORT/WAIT` kararı signal servisinde deterministik kurallarla üretilir. LLM canlı
döngüde bulunmaz.

## Dosyalar

- `schema.json`: normatif JSON Schema (Draft 2020-12)
- `examples/btc-1h-context.json`: iki servisin sözleşme testinde kullandığı ortak fixture

Örnek fixture'ın `snapshot_id` ve `content_hash` alanları producer'ın gerçek türetme
algoritmasıyla doğrulanır; temsili placeholder değildir.

## Sürüm ve uyumluluk

`v1` şeması `additionalProperties: false` kullanır. Alan silmek, alan türünü/davranışını
değiştirmek veya yeni zorunlu alan eklemek kırıcı değişikliktir ve `v2` ister. Yalnız yeni
opsiyonel alan eklemek için dahi önce iki tüketicinin ileri uyumluluğu gösterilmelidir.

Tarih alanları timezone-aware UTC'dir. `data_cutoff_at_utc`, `as_of_utc` değerinden sonra
olamaz. `directional_decision_allowed=false` iken signal servisi yönsel çıktı üretemez;
`WAIT` ve açık blocker gerekçesi üretir.

Eksik/bayat veri yalnız `required` olarak sınıflandırılmış kaynak veya katmanı etkiliyorsa
yönsel kararı kapatır. Opsiyonel kapsam eksikliği `degraded` ve `warnings` ile görünür kalır.
