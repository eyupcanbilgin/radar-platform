# ADR-0011 — Sağlık bayrağı: onarılamaz geçmişi kusur saymaz

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0006, ADR-0007, ADR-0008, Signal ADR-0044, Signal ADR-0046

## Bağlam

`producer status` ve `get_health` tek bir `healthy` bayrağı döndürür. Signal runbook'u
(11 Ağustos, MACOS-PAPER-SUPERVISION) operatöre bu bayrağa bakmayı söyler.

Canlı ölçüm (11 Ağustos 2026) bayrağın işe yaramadığını gösterdi:

```
healthy: False
OK  funding_rate_settled     ratio=1.000   backfill_and_live
OK  open_interest_value_1h   ratio=1.000   backfill_and_live
RED order_book_spread_bps    ratio=0.091   live_only
RED spot_perp_basis          ratio=0.090   live_only
```

Kırılganlığı **fiilen kapılayan** iki metrik kusursuzdu; bayrağı `False` yapan şey iki
`live_only` metrikti.

`live_only` metriklerin (spot/perp basis, order-book spread) uçta **geçmişi yoktur**: Binance
bu serileri saklamaz, backfill mümkün değildir (ADR-0007). Dolayısıyla toplama başlamadan
önceki ve geçmiş kesintilerdeki boşlukları **yapısal olarak onarılamaz**. Bunları genel
sağlık bayrağına katmak bayrağı aylarca `False` tutar.

Bu, bugün düzeltilen iki kusurla **aynı sınıftır**: `git_dirty` hiçbir koşuda `False`
olamıyordu (Signal ADR-0044), coverage `status` kalıcı olarak `degraded`dı. **Her zaman aynı
değeri veren bir sağlık göstergesi hiçbir şeyi korumaz; operatöre onu görmezden gelmeyi
öğretir.**

## Kararlar

### 1. Beklenti, metriğin geçmişinin onarılabilir olup olmamasına göre tanımlanır

`MetricCoverage.meets_expectation`:

- **`backfill_and_live`** → tam sağlık aranır (`complete`, `gap_ok`, `fresh`). Bu metriklerde
  boşluk gerçek bir kusurdur ve `backfill` komutuyla kapatılabilir.
- **`live_only`** → yalnız **tazelik** aranır. Bu metrikten beklenebilecek tek şey "hâlâ
  topluyor mu"dur; geçmiş boşluğu için yapılabilecek bir şey yoktur.

Genel `healthy` bayrağı artık `meets_expectation` üzerinden hesaplanır
(`producer.py`, `server.py`).

### 2. Ayrıntı gizlenmez

`complete`, `gap_ok`, `fresh` ve `healthy` alanları raporda **aynen durur**; rapora ek olarak
`meets_expectation` yazılır. Değişen tek şey genel bayrağın neye baktığıdır. Bir `live_only`
metriğin kapsama oranı düşükse bu görünür kalır — gelecekteki ablation için o oran anlamlıdır
(Faz 2: "basis, spread/depth ailelerini yeterli canlı geçmişten sonra ayrı ablation").

### 3. Bayrak gevşetilmez

Duran bir `live_only` toplayıcı hâlâ sağlıksızdır: tazelik gerçek sorudur. Kusurlu bir
`backfill_and_live` metrik hâlâ bayrağı `False` yapar. Test her ikisini de açıkça korur.

## Kanıt

Sentetik testler (`tests/test_coverage_health_basis.py`): `live_only` metrik onarılamaz
geçmişle beklentiyi karşılar · **durmuş** `live_only` toplayıcı karşılamaz · doldurulabilir
metrikte boşluk hâlâ kusurdur · payload her iki alanı da gösterir · 11 Ağustos'un gerçek
tablosu eski kuralla `False`, yeni kuralla `True` verir · bozuk bir feature hâlâ genel bayrağı
`False` yapar.

Canlı doğrulama, düzeltmenin **işe yaradığını beklenmedik bir biçimde** gösterdi: gürültü
kalkınca bayrak gerçek ve **eyleme dönüştürülebilir** bir soruna işaret etti —
`spot_close` (`backfill_and_live`) 7 günlük pencerede 162/168 saat taşıyor, boşluk
`2026-08-11T00:00Z → 03:00Z`. Bu boşluk `backfill --spot-days` ile kapatılabilir; eskiden
`live_only` kırmızılarının altında görünmezdi.

## Sonuçlar ve sınırlar

`healthy` bayrağı artık ulaşılabilir bir hedeftir ve `False` olduğunda **yapılacak bir şey
olduğu** anlamına gelir.

Bu ADR hiçbir eşiği gevşetmez, kapsama beklentisini düşürmez ve `live_only` metriklerin
ablation için yeterli geçmişe ulaşması gerektiği gerçeğini değiştirmez.
