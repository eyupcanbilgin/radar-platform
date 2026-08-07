# ADR-0040 — F-0001 Forward Runtime Aktivasyonu

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030–ADR-0039

## Bağlam

F-0001 forward defteri için kod, supervision ve coverage parçaları hazırdı; fakat planın
işletim maddesi gerçek başlangıç sonrası ardışık saat kanıtı oluşmadan kapatılamazdı. macOS
runtime ayrı temiz checkout, ayrı state root ve secret içermeyen console teslimat moduyla
aktive edildi. İlk venv yol hatası ADR-0038 ile düzeltildi.

## İşletim kanıtı

7 Ağustos 2026 13:00 UTC kesiminde:

- mühürlü combined baseline SHA-256:
  `66c45931282083635e2939cf3235b0d38b81ce4016f80450d9076135011a0ba8`;
- append-only defterde 11:00, 12:00 ve 13:00 UTC için üç ardışık gerçek satır vardır;
- üç satırın da status değeri `unavailable`, triggered değeri `null`dır;
- coverage 3/14 (`0.2142857143`), geçmiş kurulum öncesi 11 saat eksik ve blocker olarak
  korunmuştur;
- coverage `status=degraded`, direction `null`, outcome/Registry/alert bayrakları `false`tur;
- producer son due 13:00 context'ini yayınlamış ve `hours_behind=0` raporlamıştır;
- coverage ajanı tek-sefer koşusunu exit 0 ile tamamlamış; producer, hourly Signal ve pump
  daemon'ları çalışır durumdadır.

Kanıt kesimindeki coverage JSON SHA-256 değeri
`cbbf607d2f77572c20dd3c255e86bec2d18b3717f0f2c948f4bdc71e31bd968e`, forward ledger
dosya SHA-256 değeri
`5daea2bf9e1d217a36034a4145701ee997376e9749b63933a0a7bc94d6362c21`dir. Bunlar büyüyen
runtime state'in tarihsel kesim kimlikleridir; repoya state/ham veri alınmaz.

## Karar

1. “Saatlik gerçek context'leri deftere bağla ve coverage izle” işletim maddesi tamamlandı.
   Bu, coverage'ın sağlıklı veya kalibrasyonun hazır olduğu anlamına gelmez.
2. Kurulum öncesi 00:00–10:00 UTC saatleri backfill edilmez; kalıcı missing blocker olarak
   tutulur.
3. İlk üç unavailable gözlem tetiksiz/sakin olay sayılmaz. `triggered=null` korunur ve
   precision/recall ya da kalibrasyon paydasına alınmaz.
4. Metrik raporu için yeterli available/olgun olay oluşana kadar Faz 2 kalibrasyon ve ürün
   uyarı kartı kapıları açık kalır.

## Sonuç

Forward kanıt toplama hattı gerçek saatlerle işletimdedir; eksik/yetersiz sonucu unavailable
tutma kuralı canlı state üzerinde doğrulanmıştır. Bu ADR performans, yön veya kalibrasyon
başarısı iddia etmez.
