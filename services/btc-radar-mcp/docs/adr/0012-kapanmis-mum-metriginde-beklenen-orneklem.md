# ADR-0012 — Kapanmış-mum metriğinde yarım periyot beklentiye girmez

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0007, ADR-0008, **ADR-0011 (bu ADR onu tamamlar)**

## Bağlam

ADR-0011 `healthy` bayrağını onarılamaz geçmişten kurtardı ve şunu iddia etti:

> "`healthy` bayrağı artık **ulaşılabilir bir hedeftir** ve `False` olduğunda yapılacak bir
> şey olduğu anlamına gelir."

Canlı ölçüm bu iddiayı **yanlışladı**. Gürültü kalktıktan ve gerçek spot boşluğu backfill ile
kapatıldıktan sonra bile bayrak `False` kaldı:

```
11:17:27Z
spot_close               expected/observed 168/167   newest 2026-08-11T10:00Z
open_interest_value_1h   expected/observed 168/168   newest 2026-08-11T11:00Z
```

`spot_close` için `max_gap = 1.0 saat` (normal), `gap_ok = True`, `fresh = True`. **Gerçek
boşluk yoktur.** Fark tamamen sayaç aritmetiğindendir.

Sebep: `spot_close` **kapanmış mumdan** türer (ADR-0007 look-ahead yasağı). 11:17'de 11:00
mumu henüz kapanmamıştır ve onu beklemek yasaklanan şeyin ta kendisidir. Anlık OI ise bir
snapshot'tır; 11:00 kovası saat içinde vardır.

`expected_samples = window // period` sayacı bu ayrımı görmez ve içinde bulunduğumuz yarım
periyodu her metrikten bekler. Kapanmış-mum metriği bunu **hiçbir zaman** sağlayamaz;
`complete` kalıcı olarak `False`, dolayısıyla `healthy` de kalıcı olarak `False` olur.

Bu, bugünün dördüncü ve aynı sınıftan kusurudur (`git_dirty`, coverage `status`, `healthy`).

## Kararlar

### 1. Örnekleme kipi metrik özelliğidir

`CollectionMetricSpec.sampling_mode`:

- **`snapshot`** (varsayılan) — metrik içinde bulunduğumuz periyodun örneğini taşıyabilir.
- **`closed_bar`** — taşıyamaz; periyot kapanana kadar mum yoktur.

`spot_close` config'de `closed_bar` olarak işaretlenmiştir. Kip, `history_mode` ile aynı
desende config'de yaşar; kodda metrik adına göre tahmin yürütülmez.

### 2. Beklenen sayaç yalnız yarım periyodu düşer

`closed_bar` metrikte `expected_samples` bir azaltılır. Bu **tolerans değildir**: kapanmamış
bir mumu beklemek look-ahead olurdu, dolayısıyla o örnek beklentinin parçası değildir.

### 3. Muafiyet yalnız yarım periyoda

Gerçek eksik saat hâlâ kusurdur. Test bunu açıkça korur: 24 saatlik pencerede 20 gözlem
taşıyan bir `closed_bar` metrik `expected=23` karşısında `complete=False` ve
`meets_expectation=False` kalır.

## Kanıt

Sentetik testler (`tests/test_coverage_health_basis.py`, bellek içi PIT): aynı veriyle
`snapshot` sayacı eksik görür, `closed_bar` görmez (`expected` farkı tam 1) · gerçek boşluklu
`closed_bar` metrik hâlâ başarısız olur. Düzeltme devre dışıyken **iki test de kırmızıdır**.

Canlı doğrulama, düzeltmeden önce spot boşluğunun `backfill --spot-days` ile kapatılmasını da
içerir: `spot_close` kapsaması 0.964 → 0.994'e çıktı (85 satır), forward ve karar defterlerinin
SHA-256 değerleri **değişmedi**.

## Sonuçlar ve sınırlar

ADR-0011'in iddiası artık doğrudur: `healthy` ulaşılabilir bir hedeftir.

Bu ADR hiçbir eşiği gevşetmez ve `live_only` metriklerin ablation için yeterli canlı geçmişe
ulaşması gerektiği gerçeğini değiştirmez. Yalnız "kapanmamış bir mumu beklemek" ile "veri
eksik" durumlarını birbirinden ayırır.
