# ADR-0022 — F-0001 Provenance Bağlı Event-Row Üreticisi

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0004, Signal ADR-0021, F-0001

## Karar

1. `scripts/fragility_event_rows.py`, exact-hour `decision-context/v1` girdilerinden göreli
   kırılganlık tetiklerini ve saatlik venue OHLCV'den +24h volatilite olay etiketlerini üretir.
2. Context yalnız `data_cutoff_at_utc <= as_of_utc`, `direction=null` ve kapalı yön kapısıyla
   kabul edilir. Null kırılganlık baseline'a çevrilmez.
3. Tetik yüzdeliği yalnız geriye dönük dağılımdan gelir. Cooldown içindeki yüksek saatler
   yanlış `triggered=false` satırı olmaz; örneklemden çıkarılır.
4. Etiket eşiği yalnız karar anında sonucu settled olmuş geçmiş genişleme oranlarından gelir.
   OHLCV saatlik, kesintisiz, tekil ve kapanıştan önce yayımlanmamış olmalıdır.
5. Binance futures ve Coinbase spot birlikte zorunludur. Context, venue girdileri, config ve
   çağıranın sağladığı dataset/code provenance değerleri SHA-256 ile artefakta bağlanır.
6. Çıktı direction alanını daima null taşır; Registry'ye yazmaz ve gerçek verdict üretmez.

## Sonuçlar

ADR-0021 evaluator'ına girecek satırlar deterministik ve denetlenebilir biçimde üretilebilir.
Gerçek veri koşusu, manifest doğrulaması ve Registry kaydı sonraki ayrı kanıt işidir.
