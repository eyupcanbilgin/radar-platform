# ADR-0047 — F-0001 hazırlık projeksiyonu: bağlayıcı kısıt gözlem değil tetiktir

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0029, ADR-0030, ADR-0033, ADR-0040, ADR-0041, Platform ADR-0006

## Bağlam

Ürün sahibinin tekrar eden sorusu "ürün ne zaman hazır olur?" idi. Bu soruya bugüne kadar
kanıtla cevap verilemiyordu: `f0001_forward_coverage.py` "neredeyiz?" sorusunu yanıtlıyor,
"bu hızla ne zaman?" sorusunu yanıtlayan bir araç yoktu.

10 Ağustos'ta verilen ilk sözlü tahmin (`~10 Eylül`) yalnız `trigger.min_observations = 720`
şartına bakıyordu ve **yanlıştı**. Eşiklerin birbiriyle etkileşimi gözden kaçmıştı.

## Bulgu: eşikler birbirini zorluyor

`config/fragility_calibration.yaml`:

- `trigger.min_observations = 720` (30 gün × 24 saat)
- `trigger.episode_cooldown_hours = 24` → tetikler epizodiktir, **günde en fazla bir tane**
- `validation.min_triggered_events_per_venue = 30`

Aritmetik sonuç: 720 gözlem saatinde cooldown yüzünden **en fazla 30 tetik** olabilir. Şart
tam 30 olduğuna göre, gözlem eşiği karşılandığında tetik eşiği **ancak her gün tetik olursa**
karşılanır. İki eşik pratikte birbirini zorlamaktadır.

Gerçek oran çok daha düşüktür. ADR-0029'un mühürlü ana context setinde ölçülen değer:
**1 743 kullanılabilir context → 10 bağımsız tetik**, yani tetik başına ~174 saat (~7,3 gün).
Bu orana göre 30 tetik için gereken kullanılabilir gözlem ≈ **5 229 saat ≈ 218 gün**.

Yani **bağlayıcı kısıt gözlem sayısı değil, tetik sayısıdır** ve ölçüm tarihi 30 gün değil,
ay ölçeğindedir.

## Kararlar

### 1. Projeksiyon araç hâline getirilir, sözlü tahmin edilmez

`scripts/f0001_readiness_projection.py` defterden okur, her şartın mevcut/gerekli değerini,
gözlenen oranı, projekte edilen tarihi ve bağlayıcı kısıtı raporlar. Atomik JSON yazar.
Sonuç okumaz, Registry'ye yazmaz, yön üretmez.

### 2. Yetersiz örneklemden tarih üretilmez

Oranı takvim tarihine çevirmek için en az 48 kullanılabilir gözlem şartı vardır. Bunun
altında rapor `insufficient_sample` der ve `eta_utc` alanı `null` kalır. 3 gözlem ve 0
tetikten tarih türetmek, cevap vermemekten kötüdür: yanlış bir kesinlik üretir.

### 3. Tarihsel oran açıkça etiketlenir

ADR-0029'un oranı referans olarak raporlanır fakat `"tarihsel referans; forward ölçüm
değildir"` notuyla. Forward oran hesaplanabilir hâle geldiğinde asıl ölçüm odur; tarihsel
oran onun yerine geçmez.

### 4. Yapısal tavan raporun birinci sınıf alanıdır

`structural_ceiling.requires_trigger_every_cooldown_window` alanı, eşiklerin birbirini
zorladığı durumu açıkça bildirir. Bu bilgi bir dipnot değildir: ürün takvimini belirleyen
şeydir.

### 5. Eşikler DEĞİŞTİRİLMEZ

Bu ADR bir bulgu kaydıdır, eşik gevşetme önerisi **değildir**. `min_triggered_events_per_venue`
veya `episode_cooldown_hours` sonuç görüldükten sonra değiştirilirse ön-kayıt anlamını yitirir.
Eşiklerin gerçekçiliği ürün sahibinin ayrı ve bilinçli bir kararıdır; bu araç yalnız kararı
kanıtla besler.

## Kanıt

Tamamen sentetik testler (`tests/test_f0001_readiness_projection.py`; ağ, `user_data/` veya
canlı defter bağımlılığı yok): yetersiz örneklem tarih üretmez · yeterli örneklem tarih üretir ·
cooldown tavanı raporlanır · gözlem eşiği karşılanınca bağlayıcı kısıt `triggers` olur ·
`unavailable` gözlemler paydaya girmez · tarihsel referans etiketlidir · rapor sonuç okumaz ·
her şey karşılandığında `measurement_ready=true`.

Canlı defterle koşuldu (11 Ağustos 2026, kesim `2026-08-10T21:00Z`): 24 kayıtlı gözlemin
3'ü kullanılabilir, 0 tetik; `rate_sample_sufficient=false` olduğu için tarih üretilmedi;
`requires_trigger_every_cooldown_window=true`; tarihsel orana göre kalan 30 tetik için
5 229 kullanılabilir gözlem saati gerekiyor.

## Sonuçlar ve sınırlar

Ürün takvimi hakkındaki cevap düzeltildi: kırılganlık kalibrasyonu **30 gün değil, mevcut
kanıta göre ay ölçeğinde** bir iştir ve tarihi tetik oranı belirler.

Bu ADR performans, yön veya kalibrasyon başarısı iddia etmez. Tetik oranının forward dönemde
tarihsel orandan farklı çıkması mümkündür; araç tam da bunu ölçmek için vardır. Yeterli
örneklem oluştuğunda rapor tarihsel referans yerine gerçek forward oranı kullanacaktır.
