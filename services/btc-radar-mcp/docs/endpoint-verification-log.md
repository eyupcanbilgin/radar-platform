# Endpoint doğrulama kanıt kütüğü

Günlük `MCP Smoke` iş akışı GitHub-hosted runner'dan koşar ve o bölge Binance/Bybit
tarafında coğrafi olarak engellidir (ADR-0009). O koşu **yeşil** görünür ama Binance
zinciri için **kanıt üretmez** — engellenen kontroller `blocked_in_environment` sayılır.

Bu kütük, o boşluğun tek kapatıcısıdır: **engellenmemiş bir ağdan** koşulmuş, hiçbir
kontrolü engelli olmayan doğrulamaların tarihli kaydı. Yalnız `--record` bayrağı yazar ve
kapı kapalıdır — engelli ya da kırık bir koşu buraya giremez (ADR-0013).

Kütük **append-only**dir: geçmiş girdi düzeltilmez, yeni koşu sona eklenir. Ham piyasa
verisi (yanıt gövdeleri) buraya girmez; yalnız kontrol kimliği, HTTP durumu ve SPEC
referansı tutulur (platform CLAUDE.md kural 2).

## 2026-08-11T11:47:05+00:00 — commit `88256f9`

- **Ağ:** engelli değil — hiçbir kontrol `blocked_in_environment` dönmedi.
- **Kapsam:** 28 kontrol, tam (bitcoin-data dâhil).
- **Sonuç:** 28 OK, 0 zorunlu FAIL, 0 warn.

| check | HTTP | SPEC |
|---|---|---|
| binance_oi | 200 | SPEC:43 |
| binance_oi_hist | 200 | SPEC:43 |
| binance_premium_index | 200 | SPEC:44 |
| binance_funding_hist | 200 | SPEC:44 |
| binance_global_ls_ratio | 200 | SPEC:45 |
| binance_top_ls_position | 200 | SPEC:45 |
| binance_taker_ratio | 200 | SPEC:46 |
| binance_forceorders_removed | 404 | SPEC:47 |
| bybit_oi | 200 | SPEC:48 |
| bybit_funding_hist | 200 | SPEC:48 |
| binance_futures_depth | 200 | SPEC:80 |
| chainexposed_html | 200 | SPEC:57 |
| coinbase_ticker | 200 | SPEC:63 |
| binance_spot_price | 200 | SPEC:63 |
| binance_spot_klines | 200 | SPEC:97 |
| upbit_ticker | 200 | SPEC:64 |
| fx_erapi | 200 | SPEC:64 |
| fx_frankfurter | 200 | SPEC:64 |
| fx_fawazahmed | 200 | SPEC:64 |
| coingecko_global | 200 | SPEC:70 |
| coingecko_markets | 200 | SPEC:71 |
| binance_ethbtc | 200 | SPEC:72 |
| alternative_me_fng | 200 | SPEC:77 |
| cbbi_latest | 200 | SPEC:78 |
| bitcoin_data_openapi | 200 | SPEC:54-56 |
| bitcoin_data_sth_sopr | 200 | SPEC:54-56 |
| bitcoin_data_whale_balance | 200 | SPEC:54-56 |
| bitcoin_data_liquidation | 200 | SPEC:54-56 |
