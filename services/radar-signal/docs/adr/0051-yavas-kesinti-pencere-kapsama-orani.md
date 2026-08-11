# ADR-0051 — Yavaş kesinti: sağlık anlık boşluğu değil pencere oranını ölçer

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0042 (kesinti dedektörü), ADR-0033 (forward coverage), ADR-0041,
  MCP ADR-0012, Signal ADR-0038

## Bağlam

11 Ağustos 2026'da forward kanıt defterinin gerçek durumu şuydu:

```
expected_hour_count            109
recorded_observation_count      30
available_observation_count      9     ← ölçüme giren
unavailable_observation_count   21
missing_hour_count              79
```

Yani gözlem başlangıcından bu yana geçen 109 saatin **yalnız 9'u** kullanılabilir kanıta
dönüşmüştü. Aynı anda `runtime-health.json` şunu diyordu:

```json
{"healthy": true, "active_incidents": []}
```

Sağlık kütüğünün tamamı incelendiğinde: **106 koşudan 104'ü "olay yok" demiş**, yalnız
ikisinde olay çıkmış (03:46'da 2 saatlik, 11:06'da 10 saatlik durma).

### Neden sessizdi

ADR-0042'nin iki koşulu da **anlık** boşluğu ölçer: `forward_stalled` son gözlemin kaç saat
geride olduğuna, `producer_behind` son yayının due saatten kaç saat geride olduğuna bakar.
Eşikler sıkıdır (2 saat / 1 saat) ve doğrudur.

Ama üç saatte bir yayınlayan bir runtime, örnekleme anlarının çoğunda **"1 saat geride"**
görünür — iki eşiğin de altında. Kesinti tam durma değil, **sürekli sızıntı** olduğunda
dedektör onu göremez. Kaybedilen şey ise tam olarak fazın beklediği kanıttır.

### Kök neden (ayrı bir ders)

Sızıntının kaynağı ağ ya da uyku değildi: **kurulu paket ile config sürümü ayrışmıştı.**
Runtime checkout `88256f9`'a güncellenmişti (MCP ADR-0012, `signal_rules.yaml` içine
`sampling_mode: closed_bar` ekliyor) ama `venvs/mcp` içindeki `btc_radar` paketi eski
kurulumdu ve `CollectionMetricSpec` o alanı tanımıyordu. `extra="forbid"` doğru davranıp
reddetti:

```
1 validation error for SignalRulesConfig
collection_metrics.spot_close.sampling_mode  Extra inputs are not permitted
```

Producer stdout kütüğünde bu hatadan **6798 tane** vardı. Paket yeniden kuruldu ve yayın
aynı dakika içinde düzeldi.

Bu, kodun değil **sürecin** kusurudur: runbook checkout'u güncellemeyi anlatıyor, venv'e
paketi yeniden kurmayı anlatmıyordu. Bu ADR onu da kapatır.

## Kararlar

### 1. Yeni koşul: `forward_coverage_low`

Son `window_hours` due saatin kaçında forward gözlemi kaydedildiği ölçülür; oran
`min_ratio` altına düşerse olay üretilir. Varsayılan: **12 saatlik pencere, 0.75 taban** —
üç saatte birden seyrek yayın bu tabanın altına düşer.

Mevcut iki koşul **değişmedi ve gevşetilmedi**. Bu üçüncüsü onların göremediği rejimi
kapatır: tam durmadan sürekli saat kaybı.

### 2. Pencere gözlem başlangıcından öncesine uzatılmaz

Kurulum öncesi saatler hiçbir zaman doldurulamaz. Onları beklentiye katmak, bu depoda üst
üste düzeltilen kusurun aynısını üretirdi: `git_dirty` hiç `False` olamıyordu (ADR-0044),
coverage `status` kalıcı `degraded`dı, `healthy` hiç `True` olamıyordu (MCP ADR-0011/0012).
**Her koşuda aynı değeri veren gösterge hiçbir şeyi korumaz.**

Bu yüzden pencere `max(pencere başlangıcı, observation_start_utc)` ile kırpılır. Test bunu
açıkça korur: başlangıçtan 4 saat sonra pencere 12 değil 5 saattir ve 5/5 tamdır.

### 3. Oran yetkili kaynaktan ölçülür

Sayım coverage raporundan değil **defterin kendisinden** okunur. Rapor bayatlarsa sağlık
bayat sayılarla "iyi" görünürdü; kesintinin en olası anı da raporu üreten ajanın durduğu
andır.

Karşılaştırma metinde değil **zamanda** yapılır: defterde `Z` ekiyle yazılmış tek bir satır,
metin sıralamasında sessizce pencerenin dışına düşerdi.

### 4. Sayı yoksa oran uydurulmaz

Defter okunamıyorsa bu zaten `inputs_unreadable` olayıdır (ADR-0042 §"sessizlik sağlıklı
değildir"); kapsama koşulu ayrıca sahte bir oran üretmez. Beklenenden çok satır da oranı
1'in üstüne çıkaramaz.

### 5. Runbook'a venv yenileme adımı

`docs/MACOS-PAPER-SUPERVISION.md`, checkout güncellemesinden sonra paketlerin **yeniden
kurulması** gerektiğini ve bunun atlanmasının hangi belirtiyi verdiğini yazar.

## Kanıt

Sentetik testler (`tests/test_runtime_health_alert.py`, ağa çıkılmaz): 11 Ağustos'un gerçek
tablosunda (12 saatin 4'ü, iki anlık kontrol de temizken) olay üretilir · tam eşikte
(9/12 = 0.75) üretilmez · bir saat altında üretilir · pencere başlangıçtan öncesine uzanmaz ·
okunamayan defter sahte oran üretmez · fazla satır sağlık imal edemez · aynı pencere için
`signal_id` sabit kalır (her koşuda yeniden uyarı yok) · config aralık dışı `min_ratio` ve
eksik blok için fail-loud · dağıtılan config eşikleri taşır · okuyucu saatleri **zamana**
göre sayar (`Z` yazımı dahil) · ayrıştırılamayan saat sessizce eksik sayılmaz.

Canlı onarım (11 Ağu 2026 12:33Z): paket yeniden kuruldu, producer aynı dakika
`12.json` context'ini yayınladı; `status: ok`, `consecutive_failures: 0`.

`pytest` 462 passed, `ruff` temiz.

## Sonuçlar ve sınırlar

Bilinçli olarak **hâlâ yok**:

- **Kayıp saatlerin geri kazanılması.** Bu ADR kesintiyi görünür kılar, geçmişi doldurmaz;
  forward defteri append-only'dir ve geçmiş saat backfill edilmez (ADR-0030).
- **Sürüm ayrışmasının makine tarafından engellenmesi.** Runbook artık adımı yazıyor ama
  kurulu paket ile checkout SHA'sını karşılaştıran bir kapı yok. Bunu yapmanın doğru yeri
  producer'ın kendi başlangıç kontrolüdür ve ayrı bir karardır.
- **Uyarının okunması.** Teslimat `console` modundadır; iki olay uyarısı üretildi ve kimse
  okumadı. Telegram ayrı credential kararıdır (ADR-0049 kill-switch ile birlikte).
