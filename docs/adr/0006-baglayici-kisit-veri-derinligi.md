# ADR-0006 — Bağlayıcı kısıt veri derinliğidir; F-0001 arşiv, F-0002 ön-kayıt kapısı

- **Tarih:** 8 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0004, ADR-0005, Signal ADR-0028–0040, MCP ADR-0005

## Bağlam

6–7 Ağustos 2026 arasında PR #23–#36 merge edildi. Bu on dört PR'ın on üçü altyapıdır
(context mühürleme, readiness raporu, forward defter, launchd supervision, runtime lock,
venv symlink onarımı, coverage reporter, kart sağlığı). Ölçüm üreten tek PR #25'tir ve
sonucu `unavailable`dır. `docs/HEDEFE-GELISTIRME-PLANI.md` içinde Faz 2 altında arka arkaya
on işaretli kutucuk birikmiştir ve hiçbiri yeni ölçüm kaydetmez.

Bu bir tempo sorunu değildir. Plan bağlayıcı olmayan bir kısıtı hedeflemektedir.

### Veri asimetrisi

İki kırılganlık ailesinin kaynak gerçekliği taban tabana zıttır ve bu fark
`btc_radar/providers/binance_futures_history.py` içinde canlı API'ye karşı doğrulanmıştır:

| | `funding_stress` | `oi_buildup` |
|---|---|---|
| Endpoint | `fapi/v1/fundingRate` | `futures/data/openInterestHist` |
| Geçmiş | 400 gün geriden veri döner; ileri sayfalama | ~30 gün saklama; öncesi `-1130` sert hatası |
| Config ihtiyacı | 90g lookback, `min_span_days: 45` | 21g lookback, `min_span_days: 14`, `max_gap_seconds: 10800` |
| Bugünkü erişim | İstenildiği an, yıllarca derin backfill | Yalnız kendi PIT depomuzda olan kadar |

`openInterestHist` saklama penceresinden eski OI ancak biz sakladıysak vardır. Sürekli
toplama 4 Ağustos'ta kurulmuş, 5 Ağustos'ta beş metrikte sıfır örnekle durduğu tespit
edilmiş, runtime ancak 7 Ağustos'ta aktive edilmiştir. Bu aralıkta kaybedilen OI saatleri
kalıcıdır.

### Kilidin mekaniği

`config/fragility_calibration.yaml` her iki aileyi `features.required` altında zorunlu
tutar. Zincir fail-closed olduğu için `oi_buildup` yetersiz-geçmiş kapısına takıldığında
birleşik `snapshot.fragility` null olur, context `unavailable` olur, karar `WAIT` olur.
400 gün derinliği olan aile, 30 günle sınırlı aile tarafından rehin alınmaktadır.

ADR-0040'taki üç forward satırın `unavailable` olmasının en olası nedeni budur. Bu bir
teşhistir; çalışan runtime'ın PIT'i üzerinde ayrıca doğrulanmalıdır.

### Forward defterin sınırı

`config/f0001_forward_observation.yaml` içinde `write_experiment_registry: false` ve
`read_forward_outcomes: false`dır. Development penceresi `locked_oos_start_utc` ile
4 Ağustos'ta kilitlidir ve ADR-0029 bu tarihten sonra biriken canlı veriyi geriye dönük
Development kanıtına eklemeyi yasaklar. Dolayısıyla forward defter, ne kadar birikirse
biriksin, tasarımı gereği F-0001 verdict'ini üretemez. O bir kapsam sayacıdır, ölçüm aleti
değildir. Bu ADR bu sınırı bir kusur olarak değil, defterin doğru ve kasıtlı kapsamı olarak
kaydeder; kusur, planın bu sınırı görmeden on kutucuk boyunca defteri geliştirmeye devam
etmesidir.

### Readiness kapısı kartından sıkı

ADR-0029 madde 5, `measurement_ready=true` için ana ve iki ablation setinin tamamının tetik
örneklemi kapısını geçmesini şart koşar. F-0001 kartı §2.5 madde 5 ise ablation için yalnız
"katkı ayrı raporlanır" der. OI-only set 328 kullanılabilir context ile 0 tetik ürettiğinden
readiness yapısal olarak hiç `true` olamaz. Ön-kayıtlı kartın kabul ölçütü esastır; readiness
aracı karttan sıkı kapı koyamaz.

## Karar

1. **Projenin bağlayıcı kısıtı, kesintisiz point-in-time geçmiş derinliğidir.** Tek manşet
   metrik, her veri ailesi için "kaç gün kesintisiz geçmiş" değeridir. Diğer her iş bu
   metriği artırmadığı sürece ikincil sayılır.

2. **F-0001 `ARŞİV — ÖLÇÜLEMEZ` statüsüne alınır.** Bu ret değildir; kart hiçbir kabul veya
   ret metriği üretmemiştir. Statünün anlamı, mevcut veri kaynaklarıyla kilitli Development
   penceresi içinde ön-kayıtlı örneklem kapısının karşılanamayacağıdır. Eşikleri, yüzdelik
   sınırı, cooldown'ı ve venue şartı değiştirilmez; sonuç görülerek gevşetilmez. Harici bir
   kaynaktan meşru tarihsel OI gelirse ayrı bir kararla yeniden açılabilir.

3. **F-0002 tek-aileli funding kırılganlığı olarak ayrı ön-kayıt edilir.** Gerekçe ADR-0029'un
   kendi ifade ettiği iki meşru seçenekten ikincisidir: farklı mekanizmayı ayrı hipotez olarak
   ön-kayıt etmek. Kart F-0001'in kopyası değildir; tek aileye düşen bir hipotez daha zayıf bir
   iddiadır ve kart bunu açıkça taşır. `oi_buildup`, kendi PIT geçmişi olgunlaştığında ayrı bir
   hipotezin ablation kolu olarak değerlendirilir.

4. **Ön-kayıt iki commit kuralı F-0002 için aynen geçerlidir.** Kart yazımı/sıkılaştırması ile
   ölçüm asla aynı commit'te olmaz. Kart `feature/` dalında, PR ile ve bağımsız incelemeyle
   girer (Signal kuralı 13, ADR-0004).

5. **Toplayıcı sürekliliği P0'dır.** Kesinti bildirimi Faz 3'ten çıkarılıp öne alınır. Duran her
   saat OI tarafında kalıcı kayıptır; bu, planda ertelenebilir bir operasyon maddesi olarak
   tutulamaz.

6. **Aşağıdaki alanlar dondurulur:** runtime supervision, launchd/plist üretimi, runtime lock,
   coverage reporter, import smoke ve teslimat kartı biçimi. Mevcut hâliyle çalışır kabul edilir.
   Yeniden açılması için somut bir işletim arızası gerekir.

7. **Ölçüm kaydetmeyen ADR yazılmaz.** Altyapı kararları ADR yerine commit mesajı ve ilgili
   dosyanın kendi dokümantasyonuyla kaydedilir. Bu ADR, bu kuralı koyduğu için kendisi
   istisnadır.

8. **Faz 3 risk kapıları ertelenir.** `valid_until`, risk bütçesi, korelasyon limiti ve
   kill-switch'ler doğrulanmış bir uyarı olmadan korunacak bir şey bulamaz. Kapsam dışı
   değildir; sırası gelmemiştir.

9. **Forward defter çalışmaya devam eder, geliştirilmez.** Kapsam sayacı olarak değeri, canlı
   context sağlığının bağımsız kanıtı olmasıdır.

## Sonuçlar

Plan, ölçüm üretmeyen altyapı kutucuklarını ödüllendirmeyi bırakır. Ölçüm ufku, kesintisiz
toplamayla geçecek 7-12 aydan, hâlihazırda çekilebilir 400 günlük funding geçmişiyle
haftalar mertebesine iner. Karşılığında ürün v1'in kanıt iddiası tek aileye daralır ve bu
daralma gizlenmez.

Bu ADR performans, yön veya kalibrasyon başarısı iddia etmez. `direction` null kalır, gerçek
emir yoktur ve F-0002 ölçülene kadar ürünün kanıtlanmış bir uyarısı yoktur.
