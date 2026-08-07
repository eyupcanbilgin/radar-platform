# ADR-0007 — ADR-0006 düzeltmesi: tarihsel OI elde edilebilir, F-0001 arşivden çıkar

- **Tarih:** 8 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0006'yı kısmen geri alır; F-0001, Signal ADR-0028/0029, MCP ADR-0005

## Bağlam

ADR-0006 aynı gün kabul edildi ve tüm geliştirme planı onun üzerine yeniden yazıldı.
Merkezî iddiası, `oi_buildup` için tarihsel saatlik OI'nin elde edilemez olduğu ve bu yüzden
F-0001'in ölçülemez olduğuydu. Bu iddia, PIT deposu boş bir geliştirme makinesinde yalnız
kod ve config okunarak, canlı doğrulama yapılmadan türetildi.

Bağımsız bir ajanla çürütme incelemesi yürütüldü. İnceleme iki maddeyi düzeltti, bir maddeyi
ise yanlış olarak doğruladı. Sonrasında yapılan doğrudan doğrulama ADR-0006'nın temel
dayanağını çürüttü.

## Kanıt

`https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/` altında günlük metrics
paketleri yayımlanmaktadır. S3 listeleme API'si `2020-09-01`den `2026-08-06`ya kadar kesintisiz
`BTCUSDT-metrics-YYYY-MM-DD.zip` anahtarları döndürür. `2026-08-04` paketi indirilip açıldı;
tek CSV içerir, 289 satır (başlık + 288 beş-dakikalık kova) ve başlığı aynen şudur:

```text
create_time,symbol,sum_open_interest,sum_open_interest_value,
count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,
count_long_short_ratio,sum_taker_long_short_vol_ratio
```

`sum_open_interest_value`, `signal_rules.yaml` içinde `oi_buildup`ın beslendiği
`open_interest_value_1h` metriğinin kaynağıdır. Yani F-0001'in Development penceresinin
(`2024-01-01` → `2026-08-04`) tamamı için tarihsel OI, Binance'in kendi resmî public data
arşivinden ücretsiz elde edilebilir.

Çürütme incelemesi bu kaynağı kontrol etmiş fakat listeleme sayfası JavaScript ile
render edildiğinden boş sonuç almış ve "yayımlanmıyor" diye raporlamıştır. Ham S3 listeleme
uç noktası dosyaları göstermektedir.

Ayrıca aynı inceleme, ADR-0006'nın ikinci bir çıkarımını haklı olarak çürütmüştür:
`core/components.py` bir feature `available=False` olduğunda blocker yazıp atlar, diğer aile
bileşen olarak eklenir; `core/scoring.py` içinde `fragility` yalnız `frag_den == 0` iken
null olur. Dolayısıyla `oi_buildup` düşünce birleşik fragility null olmaz, MCP tek-aileli
kısmi skor yayımlar. ADR-0006'daki "ince aile derin aileyi rehin alıyor" mekanizması MCP
katmanında yanlıştır; rehin alma yalnız F-0001 protokol katmanında, `features.required` ve
ablation kapısı üzerinden gerçekleşir.

## Karar

1. **ADR-0006 madde 2 geri alınır.** F-0001 `ARŞİV — ÖLÇÜLEMEZ` statüsünden çıkarılır ve
   `VERİ İÇE AKTARIMI BEKLİYOR` olur. Kart ölçülemez değildir; içe aktarılmamış bir veri
   kaynağı yüzünden ölçülmemiştir. Eşiklerine, yüzdelik sınırına, cooldown'ına, venue şartına
   ve örneklem kapısına bu ADR de dokunmaz.

2. **ADR-0006 madde 1'in gerekçesi düzeltilir.** Bağlayıcı kısıt hâlâ kesintisiz PIT geçmiş
   derinliğidir, fakat nedeni "elde edilemeyen veri" değil **"içe aktarılmamış veri"**dir. Bu
   fark, doğru işi belirler: beklemek ve alarm kurmak değil, kaynağı bağlamak.

3. **ADR-0006 madde 3 (F-0002 funding-only ön-kaydı) iptal edilir.** Gerekçesi, birleşik
   hipotezin ölçülemez olmasıydı. O gerekçe ortadan kalktığı için tek-aileli hipoteze
   düşmek gereksiz bir kapsam daraltmasıdır. Ön-kayıt henüz yazılmadığı için iptalin
   araştırma disiplini açısından maliyeti yoktur.

4. **Yeni P0: `binance_vision_metrics` tarihsel OI içe aktarımı.** Zorunlu kısıtlar:
   - PIT semantiği mevcut backfill kalıbını izler (MCP ADR-0005): `available_at =
     event_time + publication_lag`, ayrı provider adı, `ingested_at` ayrı korunur. Günlük
     paketin yayın gecikmesi ölçülüp config'e yazılır; varsayılmaz.
   - 5 dakikalık kovadan saatlik seriye indirgeme, canlı `openInterestHist` semantiğiyle
     aynı olmalıdır (saat sınırındaki örnek; ortalama değil). Kural config'e yazılır.
   - **Zorunlu çakışma doğrulaması:** günlük paket ile canlı `openInterestHist` uç noktası
     ~30 gün örtüşür. İki serinin bu pencerede aynı olduğu gösterilmeden 6 yıllık geçmiş
     güvenilir sayılmaz. Doğrulama başarısızsa içe aktarım yapılmaz.
   - Ham CSV/zip git'e girmez; yalnız manifest ve hash kaydedilir.

5. **"Kalıcı kayıp" iddiası geri alınır.** Toplayıcı kesintisi artık ertesi günün paketinden
   onarılabilir. Kesinti bildirimi ve barındırma tartışması değerini korur fakat aciliyetini
   kaybeder; P0 olmaktan çıkar.

6. **ADR-0006'nın yürürlükte kalan maddeleri:** dondurma listesi (runtime supervision,
   launchd/plist, runtime lock, coverage reporter, import smoke), "ölçüm kaydetmeyen ADR
   yazılmaz" kuralı, Faz 3 risk kapılarının ertelenmesi ve forward defterin geliştirilmemesi.
   Son on dört PR'ın on üçünün altyapı olduğu tespiti geçerliliğini korur; bu ADR o eleştiriyi
   değil, altında yatan veri iddiasını düzeltir.

7. **`f0001_readiness.py` kartından sıkı kapı uygular** (çürütme incelemesi I6, doğrulandı).
   Kart §2.5/5 ablation için yalnız "katkı ayrı raporlanır" derken araç üç varyantın da 30
   tetik eşiğini geçmesini şart koşar. Ön-kayıtlı kartın ölçütü esastır; araç karttan sıkı
   kapı koyamaz. Bu, OI içe aktarımından ayrı ve bağımsız bir onarımdır.

8. **Süreç kuralı:** doğrulanmamış çıkarım üzerine plan yeniden yazılmaz. ADR-0006, canlı
   olarak kontrol edilebilecek bir veri iddiasını kontrol etmeden kabul edildi ve bir günden
   kısa sürede geri alındı. Bundan sonra bir ADR'ın dayandığı harici veri iddiası, ADR kabul
   edilmeden önce doğrudan doğrulanır ve kanıtı ADR'a yazılır.

## Açık doğrulamalar

Bu ADR aşağıdakileri doğrulanmış saymaz; madde 4'ün kapılarıdır:

- Günlük paketin gerçek yayın gecikmesi
- Paket serisi ile canlı uç nokta serisinin çakışma penceresinde eşitliği
- `2024-01-01`–`2026-08-04` aralığında paket kapsamının gerçekten kesintisiz olduğu

## Sonuç

F-0001 ölçülebilir bir hipotezdir ve önündeki tek engel yazılmamış bir içe aktarım işidir.
Bu ADR performans, yön veya kalibrasyon başarısı iddia etmez; `direction` null kalır ve
ürünün hâlâ doğrulanmış bir uyarısı yoktur.
