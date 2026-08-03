# ADR 0002 — Korea Premium için USDKRW kur kaynağı seçimi

- **Tarih:** 2026-08-03
- **Durum:** Kabul edildi (SPEC Risk 5 kapanışı; Eyüpcan onayı, CR-002 kurulum turu)

## Bağlam

Korea Premium hesabı (`SPEC §2.3`) Upbit BTC-KRW fiyatını USDKRW kuru ile USD'ye çevirmeyi
gerektirir. Kaynak anahtarsız, ücretsiz ve makul güncellikte olmalı. Faz 0 canlı
doğrulamasında (3 Ağu 2026) üç aday da çalışır durumda bulundu.

## Karar

| Rol | Kaynak | Gerekçe |
|---|---|---|
| Birincil | `open.er-api.com/v6/latest/USD` | Anahtarsız, tek istekte tüm kurlar, `time_next_update_utc` alanıyla tazelik sözleşmesi net, günlük güncelleme premium hesabı için yeterli (on-chain değil spot bağlam metriği) |
| Yedek | `api.frankfurter.dev/v1/latest?base=USD&symbols=KRW` | ECB referans kuru; kurumsal kaynak, hafta sonu güncellenmez (bilinen sınır) |
| İzlenen 3. aday | fawazahmed0/currency-api (jsDelivr CDN) | API değil CDN dosyası; SLA'sız, yalnız acil durum |

Provider davranışı: birincil 2 denemede başarısızsa yedek; ikisi de düşerse Korea Premium
`stale/missing` işaretlenir ve güven skoruna yansır (fail-closed). Kur değeri
`RawObservation.notes` alanına kaynak adıyla yazılır.

## Sonuçlar

- Kur günlük olduğundan cache TTL 6-12 saat; premium'un saat-içi oynaklığı BTC bacağından gelir,
  kur bacağından değil — bu kabul edilen bir ölçüm sınırıdır ve SPEC §2.3 notuna yansır.
- USDT/USD normalizasyonu (CR-002 P1-7) ayrı bir iştir; bu ADR yalnız KRW bacağını seçer.
