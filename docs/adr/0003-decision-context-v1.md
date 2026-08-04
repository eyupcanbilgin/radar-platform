# ADR-0003 — BTC 1h paper için `decision-context/v1`

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Hedefe Geliştirme Planı Faz 1, btc-radar ADR-0003, signal CR-002 P0-1

## Bağlam

MCP'deki `RegimeSnapshot` ve signal servisindeki `snapshot_id/regime_line` alanları aynı
kararı tarif ediyor, fakat aralarında sürümlü ve makinece doğrulanan bir taşıma sözleşmesi
yoktu. Serbest biçimli satır taşımak; alan kaybı, timezone hatası, stale verinin yönsel
karara sızması ve iki servisin sessizce farklılaşması riskini yaratıyordu.

## Karar

1. İlk ürün kapsamı `BTCUSDT · Binance USDT perpetual · 1h · paper` olarak sabitlenir.
2. Ortak sözleşme `contracts/decision-context/v1/schema.json` dosyasıdır.
3. MCP yalnız rejim/veri sağlığı bağlamı üretir; teknik setup ve nihai karar signal
   servisinde kalır.
4. Çıktı kümesi `LONG | SHORT | WAIT`tir. `directional_decision_allowed=false` iken
   signal yönsel çıktı üretemez.
5. `as_of_utc` kapanmış 1h mumdur; `data_cutoff_at_utc > as_of_utc` reddedilir.
6. Şema sıkıdır (`additionalProperties=false`). Kırıcı değişiklik yeni major sözleşme
   dizini ister.
7. Ortak fixture her iki servisin testinde okunur; üretici ve tüketici drift'i CI'da kırılır.

## Sonuçlar

- MCP kesintisi veya zorunlu veri eksikliği emir/sinyal talimatına dönüşmez; `WAIT` kapısı
  makinece taşınır.
- Yeni provider ya da strateji eklenmeden servis sınırı netleşir.
- HTTP taşıması henüz uygulanmaz; aynı JSON gövdesi ileride HTTP veya dosya/replay yoluyla
  taşınabilir.
