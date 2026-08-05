# ADR-0023 — Coinbase Spot OHLCV ve Çok-Venue Manifest

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0021, ADR-0022, F-0001

## Bağlam

F-0001 venue kırılganlığı kapısı Binance futures ile bağımsız Coinbase spot sonuç serisini
birlikte zorunlu tutar. Repoda Binance indirme yolu vardı; Coinbase BTC-USD saatlik verisini
aynı kanıt zincirine getiren anahtarsız, deterministik bir giriş ve iki venue'yu birlikte
hashleyen manifest üretimi yoktu.

## Karar

1. `scripts/download_coinbase_spot.py`, CCXT'nin public Coinbase yüzeyinden BTC/USD `1h`
   OHLCV'yi ileri pagination ile indirir; private API anahtarı kullanmaz.
2. İndirici yalnız istenen `[start, end)` aralığını tam örten kapanmış mumları kabul eder.
   Duplicate, gap, eksik uç, açık mum ve ilerlemeyen pagination fail-closed hatadır.
3. Çıktı deterministik yola atomik replace ile yazılır:
   `user_data/data/coinbase/spot/BTC_USD-1h-spot.feather`.
4. `scripts/data_manifest.py`, Binance'a özel alt dizin yerine `user_data/data/` kökünü
   tarar. Böylece yeni manifest tek bir `dataset_snapshot` altında tüm venue girdilerini
   içerir. Tarihî manifestler yeniden yazılmaz.
5. Ham veri git dışında kalır. Testler tamamen sentetiktir; bu değişiklik gerçek F-0001
   verdict'i veya Registry satırı üretmez ve Locked OOS'u açmaz.

## Sonuçlar

F-0001'in ikinci venue girdisi yeniden üretilebilir hale gelir. Gerçek ölçümden önce indirme,
yeni tarihli manifest üretimi ve `data_manifest.py --verify` aynı veri ortamında başarıyla
tamamlanmalıdır.
