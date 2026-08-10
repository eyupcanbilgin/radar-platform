# ADR-0048 — Kırılganlık uyarı kartı: bağlandı, kapısı kapalı

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030, ADR-0031, ADR-0042, ADR-0047, Platform ADR-0004, Platform ADR-0006

## Bağlam

Planın açık maddesi şuydu: *"Saatlik uyarı kartını direction üretmeden ledger/outbox hattına
bağla."* Bu madde veriye bloke **değildi** — bugün yapılabilirdi. Fakat ürün kuralı da nettir:
yeterli available/olgun forward veri yokken metrik veya uyarı kartı **üretilmez**.

10 Ağustos'ta forward hattı ilk kez `observed` satır üretmeye başladı (ADR-0041 + MCP
backfill'i sonrası). Elde 4 gözlem ve 0 tetik var. Yani kart bugün *yayınlanamaz*, ama ilk
gerçek tetik geldiğinde teslimat yolu hazır olmalıdır.

İkisi arasındaki gerilim şöyle çözüldü: **hat bağlandı, kapı kapalı bırakıldı.**

## Kararlar

### 1. Kapı config'de, kodda değil; varsayılan kapalı

`config/f0001_forward_observation.yaml` içindeki `emit_alerts` kapıyı yönetir ve `false`tur.
Kod kapıyı okur, kendi kararını vermez. Kapalıyken hiçbir şey outbox'a yazılmaz; yalnız
**sessiz kalma gerekçesi** rapora düşer (`alerts_disabled_by_config`) — sessizliğin sebebi de
kayda değer bir bilgidir.

### 2. Üç red kartın varlık sebebidir

- **Yön taşımaz.** Kırılganlık gözlemi baskının arttığını söyler, fiyatın nereye gideceğini
  değil. `direction` `None` kalır ve metin bunu **kelimelerle** söyler: yalnız yönü atlayan
  bir kart, okuyucuyu kendi yönünü uydurmaya davet ederdi.
- **`unavailable` gözlem adına konuşmaz.** O durum feature kapısının ölçmeyi reddettiği
  anlamına gelir; kart üretmek eksik veriyi sakin piyasa gibi gösterirdi. Yalnız
  `observed` + `triggered` kart üretir.
- **Yön taşıyan gözlemde fail-loud.** Böyle bir gözlem bu üründe olamaz; sessizce atlamak onu
  normalleştirirdi.

### 3. Idempotency `observation_id` üzerindedir

Kart, append-only tetik defterinin karar saati başına zaten sabitlediği `observation_id` ile
anahtarlanır. Aynı saat yeniden işlendiğinde metin bit-bit aynı üretilir ve outbox bunu güvenli
tekrar sayar. Metin yalnız o kimliğin sabitlediği alanlardan türer; `now` bilinçli olarak
metne **girmez** (outbox aynı anahtarı farklı gövdeyle reddeder — 7 Ağustos'ta gözlenen hata).

### 4. Paralel teslimat yolu açılmaz

Kart, saatlik karar ve kesinti uyarısıyla **aynı outbox**'a `fragility_warning` türüyle
yazılır; mevcut pump teslim eder. Yeni kanal, yeni secret, yeni süreç yoktur.

### 5. Kartın açılması ayrı bir üründür kararıdır

`emit_alerts` bu ADR ile açılmaz. Açılması, kalibrasyonun anlamlı veriyle geçmesini gerektirir
ve ADR-0047'ye göre bunun takvimi ay ölçeğindedir. Kapıyı erken açmak, kalibre edilmemiş bir
uyarıyı ürün gibi sunmak olurdu.

## Kanıt

Tamamen sentetik testler (`tests/test_fragility_warning.py`): config kapısı kapalıyken
tetiklenmiş gözlem bile yayınlanmaz · `unavailable` kart olmaz · tetiklenmemiş gözlem kart
olmaz · yön taşıyan gözlem fail-loud · kart yön iddiasını **kelimelerle** reddeder · kart
metninde kendi reddi dışında hiçbir işlem dili yoktur · aynı gözlem bit-bit aynı metni üretir ·
kapı açıkken bir kez kuyruğa alınır ve tekrarında idempotenttir · her sonuçta `direction=None`,
`outcome_read=False`, `registry_write=False`.

Canlı doğrulama (11 Ağustos 2026): `emit_alerts: false`; en yeni gerçek gözlem
(`2026-08-10T22:00Z`, `observed`, `triggered=False`) için kapı
`(False, 'alerts_disabled_by_config')` döndü; canlı outbox'ta `fragility_warning` türünden
**0 satır** var.

## Sonuçlar ve sınırlar

Teslimat yolu hazırdır ve ilk gerçek tetik aceleyle yazılmış koda değil, testli bir hatta
denk gelecektir. Bu ADR hiçbir uyarı yayınlamaz, kalibrasyon iddiası taşımaz ve `direction`ı
null'dan çıkarmaz.

Bilinçli olarak hâlâ yok: kartın **açılması** (ayrı ürün kararı), uzak bildirim (Faz 3),
ve kart metninin kalibrasyon sonrası içeriği — precision/recall ölçülmeden kart bir olasılık
iddiası taşımaz.
