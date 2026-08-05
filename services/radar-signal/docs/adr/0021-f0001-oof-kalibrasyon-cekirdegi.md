# ADR-0021 — F-0001 Out-of-Fold Kalibrasyon Çekirdeği

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0004, Signal ADR-0014, F-0001, SINYAL-SPEC v2.4

## Bağlam

F-0001 ön-kaydı, iki venue için kırılganlık tetiklerinin ileri volatilite olaylarıyla
kalibrasyonunu ister. Kabul metrikleri train sonucunu veya tüm dönemde öğrenilmiş olasılığı
test tahminine sızdırmadan hesaplanmalıdır. Brier olasılık formülü sonuç görülmeden F-0001
protokol v1.1'de ayrıca sıkılaştırılmıştır (`6274d9e`).

## Karar

1. `scripts/fragility_calibration.py`, hazırlanmış olay satırlarını purged walk-forward
   fold'larında değerlendirir. Her satır `as_of_utc`, `label_available_at_utc`, boolean
   `triggered` ve boolean `event` taşır.
2. Trigger=true/false olasılıkları yalnız train satırlarında, config'deki Laplace alpha ile
   öğrenilir. Baseline aynı train bölümünün koşulsuz Laplace olay oranıdır.
3. Ana metrikler yalnız pooled out-of-fold test tahminlerinden hesaplanır. Event-rate lift,
   equal-coverage recall lift, Brier skill ve pozitif fold oranı config kapılarına bağlıdır.
4. Binance futures ve Coinbase spot ayrı geçmek zorundadır; venue ortalaması alınmaz. Eksik
   venue, az tetik veya olay yokluğu `unavailable`dır; nötr/başarısız satır uydurulmaz.
5. Locked OOS satırı, duplicate karar saati, naive timestamp ve erken label availability
   fail-loud reddedilir. Çıktı direction alanını daima null taşır.
6. Bu dilim tetik veya volatilite etiketini OHLCV'den üretmez. O üretici ayrı iş paketidir;
   hazırlanmış satırların provenance doğrulaması olmadan gerçek F-0001 verdict'i üretilemez.

## Sonuçlar

Kalibrasyon matematiği sentetik veriyle deterministik olarak test edilebilir; fakat bu kod
tek başına araştırma kanıtı değildir. Gerçek veri okunmamış, Registry'ye yazılmamış ve
F-0001 kartının sonuç bölümü değiştirilmemiştir.
