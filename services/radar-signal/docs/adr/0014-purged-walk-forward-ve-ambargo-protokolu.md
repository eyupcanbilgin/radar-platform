# 0014 — Purged Walk-Forward ve Embargo Araştırma Protokolü

- **Tarih:** 5 Ağustos 2026
- **Durum:** KABUL EDİLDİ
- **İlgili:** CR-001 CR-3, CR-002 P1-3, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 2

## Bağlam

Faz 2 yönsel araştırma safhasında hipotez ailelerinin sızıntısız (leak-free) ve dürüst biçimde
ölçülmesi gerekmektedir. Geleneksel kros-validasyon veya sade walk-forward yöntemlerinde iki temel
sızıntı riski bulunmaktadır:
1. **Forward Horizon Overlap (Purge):** Etiket penceresinin (örn. +24h getiri) train setinin sonundan
   embargo veya test setinin içine sızması.
2. **Otokorelasyon Sızıntısı (Embargo):** Train penceresinin sonundaki örnekler ile test penceresinin
   başındaki örnekler arasındaki zaman kaskadı otokorelasyonu.

Ayrıca, zaman dilimi belirsizlikleri (naive timestamp) ve Locked OOS (`2026-08-04T00:00:00Z`) dönemine
yanlışlıkla erişim, araştırma sonuçlarının meşruiyetini zedeler.

## Karar

1. **Konfigürasyon Güdümlü Eşikler:** Eşikler ve sınırlar `config/research_protocol.yaml` dosyasından
   okunur; koda sabit eşik gömülemez. Min embargo süresi en az 1 gündür.
2. **Purged Walk-Forward:** Train penceresi sonunda, forward horizon etiketi ($H$ saat) train ve embargo
   sınırını aşan tüm örnekler train kümesinden temizlenir (`train_purged_end_utc = train_raw_end_utc - H`).
3. **Embargo Tamponu:** Train penceresi sonu ile Test penceresi başı arasında konfigürasyondan gelen
   en az $E$ günlük (`embargo_days >= min_embargo_days`) tampon boşluk bırakılır.
4. **Zaman Standardı:** Tüm tarih damgaları timezone-aware UTC olmak zorundadır. Unaware/naive
   timestamp kullanımı fail-loud `ProtocolValidationError` ile durdurulur.
5. **Locked OOS Koruması (Fail-Closed):** Locked OOS dönemi (`2026-08-04T00:00:00Z`) varsayılan olarak
   kilitlidir. Varsayılan CLI ve split üretici, locked OOS dönemine erişmeye çalışıldığında derhal
   `LockedOOSAccessError` fırlatır.
6. **Veri Eksikliği ve Kalite Semantiği:** Veri bulunmaması, boş pencere veya mum açığı durumunda
   "0 getiri" veya "nötr" varsayımı yapılmaz. Pencere açıkça `unavailable` veya `invalid` olarak
   raporlanır.
7. **Determinizm ve Replay:** Aynı girdiler için üretilen split planları %100 deterministiktir ve 100
   kez replay edildiğinde bit-bit aynı JSON çıktısını üretir.

## Sonuçlar

Gelecekte yazılacak hipotez aileleri için dürüst, sızıntısız ve tekrarlanabilir bir split/ölçüm
iskeleti kurulmuştur. Bu protokol yeni strateji veya yön üretmez; `experiments.jsonl` veya
`verdict_events.jsonl` registry kütüklerine sahte deney satırı yazmaz.
