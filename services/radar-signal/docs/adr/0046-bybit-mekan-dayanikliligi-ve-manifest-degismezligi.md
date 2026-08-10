# ADR-0046 — İkinci mekân (Bybit), çalışabilir venue kapısı ve manifest değişmezliği

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0020, ADR-0043, ADR-0044, ADR-0045, Platform ADR-0006

## Bağlam

Dört yönsel aile reddedildikten sonra (S-0003…S-0006) beşinci aile için mevcut veri
yüzeyinde mekanizması gerçekten bağımsız bir hipotez kalmadığı görüldü. Aday havuzu
**tahminle değil ölçümle** daraltıldı (11 Ağustos 2026):

| Aday kaynak | 2024 geçmişi | Sonuç |
|---|---|---|
| Binance `futures/data/takerlongshortRatio` | `-1130` | ~30 gün saklama; Development için ölü uç |
| Binance `globalLongShortAccountRatio` | `-1130` | aynı |
| Binance `topLongShortPositionRatio` | `-1130` | aynı |
| **Bybit v5 `market/kline`** | ✅ | tam geçmiş |
| **Bybit v5 `market/funding/history`** | ✅ | tam geçmiş |

Aynı anda ikinci ve daha önemli bir eksik görünür oldu: hipotez kartlarının **8. kabul
kriteri** mekân dayanıklılığıdır, fakat tek yürütme mekânıyla
`evaluate_period_venue_fragility` hiç koşamıyordu. S-0005 ve S-0006 bu kapıyı
`not_evaluated` raporlamak zorunda kaldı. **Hiç değerlendirilemeyen bir kriter kriter
değildir, süstür.**

## Kararlar

### 1. Beşinci aile ŞİMDİ açılmaz

Dört ailenin p-değerleri 0.27, 0.41, 0.43, 0.55'tir; hiçbiri anlamlılığa yaklaşmamıştır.
Dördü de aynı yapısal sınıftandır: tek gözlem + göreli eşik bandı + 24 saat ufuk. Aynı
sınıftan beşinciyi denemek düşük ön-olasılıkla çoklu-deneme cezasını büyütür.

Bybit'in açtığı adaylar (mekânlar arası funding ayrışması, mekânlar arası perp fiyat
dağılımı) sırasıyla S-0003 ve S-0005'e komşudur; ADR-0004 §4'ün bağımsızlık kapısını tek
başıma "yeterince bağımsız" diye geçemem. Bybit bu yüzden **yeni bir hipotez için değil,
mevcut kabul kriterini çalışır kılmak için** eklenmiştir.

### 2. Bybit perp geçmişi manifeste alınır

`scripts/download_bybit_perp.py` Bybit BTCUSDT perp 1h mumlarını indirir: 22 704 kapalı mum,
**0 eksik saat, 0 gap** — Binance perp ile birebir aynı kapsam. Sayfalama, bütünlük ve gap
raporlama yeniden yazılmaz; Coinbase ve Binance spot indiricileriyle **aynı doğrulanmış
yardımcıları** kullanır, böylece manifestteki her mekân aynı kurallarla kurulur.

### 3. Venue kapısı sinyali değil, yürütmeyi değiştirir

`scripts/venue_robustness.py` ön-kayıtlı sinyali **olduğu gibi** alır ve yalnız yürütme
fiyatlarını mekâna göre değiştirir. Sinyali her mekânın kendi fiyatlarından yeniden türetmek
sessizce ikinci bir hipotez yaratırdı.

Ölçtüğü soru gerçektir: **aynı kural başka bir yerde de para kazandırır mıydı?** Yalnız
uydurulduğu mekânda var olan bir kenar, piyasa etkisi değil mekân artefaktıdır (ücret
tarifesi, likidite, listeleme geçmişi).

Mekânda olmayan saat **doldurulmaz**; o sinyal orada gerçekleşmemiştir. Sinyal ile mekân
serisi hiç kesişmiyorsa sessizce boş dönülmez, fail-loud hata verilir — sessiz boşluk "bu
mekânda sonuç yoktu" diye okunurdu.

### 4. Manifest değişmez kanıttır; üzerine yazılmaz

Bybit eklenirken manifest yeniden üretildi ve aynı UTC gününde olduğu için
`MANIFEST-20260810.json` dosyası **üzerine yazılmak üzereydi**. O dosya dört kayıtlı koşunun
(`E-…185929`, `…190124`, `…190318`, `…205747`) `dataset_snapshot` alanının işaret ettiği
snapshot'tır (`637104fb…`).

Depo bu ilkeyi MCP context publisher'da zaten uygular (atomik no-overwrite). Manifest de aynı
disipline alındı: mevcut bir manifestin üzerine **asla** yazılmaz. İçerik birebir aynıysa yol
yeniden kullanılır (idempotent); farklıysa saat damgalı yeni dosya yazılır
(`MANIFEST-YYYYMMDDTHHMMSS.json`). Sıralama korunur — `.` (0x2E) < `T` (0x54) olduğundan
`latest_manifest_path()` en yenisini seçmeye devam eder.

Okunamayan mevcut manifest "içerik aynı" sayılmaz; sessizce üzerine yazılmaz.

## Kanıt

Tamamen sentetik testler (ağ, `user_data/` veya canlı Registry bağımlılığı yok):

`tests/test_manifest_no_overwrite.py` — ilk manifest düz tarih adını alır; aynı içerik aynı
yolu kullanır; **farklı içerik eskiyi bozmadan saat damgalı dosyaya yazılır**; saat damgalı
dosya en yeni olarak sıralanır; ertesi gün dosyası ondan sonra gelir; okunamayan manifest
üzerine yazılmaz.

`tests/test_venue_robustness.py` — aynı sinyal her mekânda yürütülür; kötü fiyatlı mekân
daha kötü sonuç verir; eksik saat uydurulmaz; kesişme yoksa fail-loud; boş mekân kümesi ve
eksik `signal` kolonu reddedilir.

Canlı doğrulama: eski snapshot `637104fb…` (5 dosya) **korundu**, yeni snapshot
`4397132c…` (6 dosya) ayrı dosyaya yazıldı, `--verify` yeni manifest için `ok` döndü.

## Sonuçlar ve sınırlar

Mekân dayanıklılığı kapısı artık **koşabilir** durumdadır; bir sonraki ailede base ayakta
kalırsa gerçekten değerlendirilecektir. Bu ADR hiçbir hipotezi kabul veya reddetmez, geçmiş
retleri değiştirmez ve alpha iddiası taşımaz.

Bilinçli olarak hâlâ yok:

- **Beşinci yönsel aile.** Bağımsız mekanizma havuzu mevcut veri yüzeyinde tükenmiştir;
  order-book likidite asimetrisi yeterli canlı geçmiş biriktiğinde (şu an `ratio≈0.05`)
  değerlendirilebilir.
- **Bybit funding geçmişi.** Uç doğrulandı fakat indirilmedi; şu an bir hipoteze bağlı
  olmadan veri eklemek kapsam genişletmesi olurdu.
- **Geçmiş ailelerin yeniden koşulması.** S-0005/S-0006 reddedilmiştir; venue kapısını
  onlara geriye dönük uygulamak sonucu değiştirmez.
