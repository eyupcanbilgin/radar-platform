# ADR-0041 — Uyanma sonrası context yayın yarışı ve sınırlı bekleme

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0032, ADR-0033, ADR-0040, MCP ADR-0006

## Bağlam

ADR-0040 forward runtime'ı aktive etti. 10 Ağustos 2026 15:35 UTC kesiminde coverage
`degraded` raporladı: `expected=88`, `recorded=18`, `missing=70`, `available=0`, son gözlem
**2026-08-09T22:00Z**. Süreçler launchd'de `running` görünüyordu.

Teşhis, "running" durumunun sağlık kanıtı olmadığını bir kez daha gösterdi; fakat arıza da
bir kod çökmesi değildi:

- `signal-hourly.stderr` son yazım **7 Ağustos 17:02**. Oradaki `jsonschema` (ADR-0038
  öncesi) ve `outbox idempotency` hatalarının **ikisi de tarihîdir**, güncel arıza değildir.
- Karar defteri 10 Ağustos'ta çalışmaya devam etti (01, 04, 07, 10, 12, 15 UTC — hepsi WAIT),
  fakat **hepsinin `context_snapshot_id` alanı boştur**.
- Aynı saatlerin stdout kaydı `context_status=missing` ve
  `f0001_forward_observation.recorded=false` (`status=context_unavailable`) der.
- Aug 9 16:00 da boş context'liydi ve onun da forward gözlemi yoktur — korelasyon birebirdir.

### Kök neden

Host pilde ve neredeyse sürekli Deep Idle uykusundadır (`pmset`: her ~17 dakikada yalnız
2–14 saniyelik DarkWake). Producer `collect` kütüğü bunu doğrular: 13:12 → 15:29 arası hiç
koşmamıştır, oysa aralık 300 saniyedir.

Bundan iki ayrı mekanizma doğar:

1. **Atlanan saatler.** Producer `--catch-up-hours 0` ile her uyanışta yalnız güncel saati
   yayınlar, gerisini açıkça `skipped` yazar (heartbeat'te 24 skipped publish). Bu, ADR-0006
   madde 5'in bilinçli davranışıdır ve `missing_forward_hours:70` bundandır.
2. **Yayın yarışı (asıl kusur).** MCP ADR-0006 madde 1, producer grace'inin (90 sn) Signal
   grace'inden (180 sn) küçük olmasına dayanarak "tüketici dosyayı aradığında artefakt
   yerinde olur" garantisini verir. **Bu garanti host uyku/uyanmasından sonra geçersizdir:**
   iki daemon aynı anda devam eder ve her biri bağımsızca "şu an due" hesaplar; aradaki
   90 saniyelik tampon hiç yaşanmaz.

Kanıt: 15:29:46 UTC'de host `UserActivity` ile FullWake oldu. Signal 15:00 kararını
**15:29:49**'da yazdı; producer 15.json'u **15:29:51**'de yayınladı. Fark iki saniyedir.

Karar defteri append-only ve `UNIQUE (symbol, timeframe, as_of_utc)` kısıtlıdır. Dolayısıyla
context'siz yazılan bir saat **kalıcı olarak** context'sizdir; 10 Ağustos'un altı kararı artık
düzeltilemez.

## Kararlar

### 1. Daemon, context'i sınırlı süre bekler

`UtcHourlyScheduler` daemon döngüsü, bir saatin kararını yazmadan önce context'in
yayınlanmasını `context_wait_seconds` (varsayılan 240) kadar bekler; `context_poll_seconds`
(varsayılan 5) aralıkla yoklar. Bütçe dolduğunda karar **bugünkü gibi fail-closed yazılır**.

Bekleme, yalnız `missing` durumunda yapılır. `invalid`/`io_error` artefaktın var ama bozuk
olduğunu söyler; beklemek onu düzeltmez, fail-closed hemen çalışmalıdır. Yoklamanın kendisi
hata verirse de beklenmez — davranış bugünküne iner ve gerçek durumu yetkili okuma
(`process_hour`) deftere yazar.

### 2. Bütçe saat sınırından değil, ilk gözlem anından ölçülür

Uykudan uyanışta duvar saati saat sınırının çok ötesindedir (15:00 sınırı, 15:29 uyanma) ama
producer o anda yayına yeni başlar. Bütçeyi sınırdan ölçmek onu daha doğarken tüketirdi. Bu
yüzden bütçe, o saatin **ilk kez context'siz görüldüğü andan** ölçülür.

### 3. Bekleme kendi yuvasını asla aşmaz

İnceleme sırasında bulunan kusur: bütçe yalnız süreyle sınırlanırsa, saat sınırına yakın
uyanışta beklenen saat **hiç yazılmadan** düşebiliyordu. Örnek: 15:00 yuvası ilk kez
15:59:50'de context'siz görülür; 240 sn'lik bütçe 16:03:50'ye kadar sürer, oysa 16:03:00'da
`latest_due_hour` 16:00'a ilerler ve 15:00 sessizce kaybolur.

Bu, düzeltilmeye çalışılan kusurdan **daha kötüdür**: eski davranış o saati hiç değilse
context'siz kaydediyordu. Saat kaybetmek, saati context'siz yazmaktan kötüdür. Bu yüzden
bekleme, bir sonraki yuva due olmadan (`due + 1 saat + grace`, bir yoklama payı bırakarak)
kesilir ve saat fail-closed yazılır.

### 4. Deterministik çekirdek değişmez

`HourlyDecisionRuntime.process_hour` ve `run_once` **hiç değişmemiştir**. Bekleme yalnız
daemon yuva ilerletmesindedir. Replay determinizmi ve tek-sefer koşusu aynen korunur;
`--context-wait-seconds 0` eski davranışı birebir geri verir.

### 5. Eksik saatler backfill edilmez

9 Ağustos 22:00 UTC sonrası oluşan boşluk **doldurulmaz**. ADR-0040 madde 2 aynen geçerlidir:
kurulum/kesinti öncesi saatler kalıcı missing blocker'dır. Producer `--catch-up-hours 0`
olarak **kalır**; ürün sahibi kararıdır. Geç üretilmiş bir context'in canlı gözlem sanılması
riski, kapsama açığından daha ağırdır.

### 6. Bekleme parametreleri zamanlama bütçesidir, sinyal eşiği değildir

`grace_seconds` ile aynı desende modül varsayılanı + CLI bayrağıdır. "Eşikler config'de ve
göreli yüzdelik" kuralı tetik/skor eşiklerini bağlar; bunlar ölçüm eşiği değil, işletim
zamanlama bütçesidir ve hiçbir sinyal kararına girmez.

## Kanıt

Sentetik regresyon testi (`tests/test_hourly_runtime.py`, sahte saat + sahte context kaynağı
+ bellek içi defter; ağ ve `user_data/` bağımlılığı yoktur):

- `test_daemon_waits_for_late_context_instead_of_burning_the_hour` — düzeltme devre dışıyken
  `assert ['missing'] == ['ready']` ile kırmızıdır; yani 10 Ağustos arızasını birebir üretir.
- `test_daemon_records_fail_closed_once_the_context_wait_budget_expires` — bekleme sınırsız
  değildir; bütçe dolunca saat WAIT + blocker ile yazılır, askıda kalmaz.
- `test_daemon_does_not_wait_for_a_context_that_exists_but_is_broken` — `invalid` beklemez.
- `test_context_wait_zero_preserves_previous_immediate_behaviour` — eski davranış korunur.
- `test_context_wait_never_outlives_its_own_hour_slot` — koruma kapatıldığında scheduler
  12:00 yuvasını hiç yazmadan 13:00'a geçerek kırmızı olur; yani saat kaybını yakalar.
- `test_scheduler_rejects_invalid_context_wait_configuration` — sınır doğrulaması.

## Sonuçlar ve sınırlar

Bu ADR **yalnız yarışı** çözer. Atlanan 70 saatin tek sebebi host uykusudur ve kodla
çözülmez; işletim kararıdır (ürün sahibi "Mac'i uyanık tut" seçeneğini seçmiştir, uygulama
ayrı bir işletim adımıdır).

Bu ADR performans, yön veya kalibrasyon başarısı iddia **etmez**. Kaydedilmiş 18 gözlemin
tamamı `funding_stress:history_gap` ve `oi_buildup:history_gap` yüzünden zaten `unavailable`
olduğundan `available_observation_count` hâlâ 0'dır. Faz 2 kalibrasyon ve ürün uyarı kartı
kapıları, yeterli available/olgun olay oluşana kadar **kapalı kalır**. `direction` null'dır.
