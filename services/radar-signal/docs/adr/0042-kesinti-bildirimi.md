# ADR-0042 — Kesinti bildirimi: duran duruma değil, duran ilerlemeye alarm

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0033, ADR-0037, ADR-0040, ADR-0041, MCP ADR-0006

## Bağlam

ADR-0041'in teşhisi sırasında ortaya çıkan asıl operasyonel açık şuydu: forward defteri
**2026-08-09T22:00Z**'den beri donmuştu ve bu **10 Ağustos 15:35Z**'ye kadar, yani yaklaşık
**17 saat** boyunca fark edilmedi. Dört launchd ajanının dördü de `running` görünüyordu.

MCP ADR-0006 bu boşluğu zaten adıyla kaydetmişti: *"Alarm/bildirim. Kesinti kütüğe yazılır;
kimseyi uyandırmaz."* Kesintinin bedeli doğrudan Faz 2'nin beklediği kanıttır: kaçan saat
geri gelmez (ADR-0040 madde 2, backfill yok).

## Kararlar

### 1. Alarm duran DURUMA değil, duran İLERLEMEYE bakar

Bu paketin en önemli kararı **neye alarm bağlanmayacağıdır**.

Coverage `status` alanı kalıcı olarak `degraded`tır: runtime kurulumundan önceki saatler
hiçbir zaman doldurulamaz ve `missing_forward_hours` blocker'ı kalıcıdır. Buna alarm
bağlansaydı uyarı **her koşuda** çıkar, operatör alarmı görmezden gelmeyi öğrenir ve gerçek
kesinti geldiğinde de görmezdi. Gürültü, alarmın kendisini işlevsiz kılar.

Bu yüzden izlenen şey durum değil ilerlemedir:

- `forward_stalled` — forward defteri `stall_hours`tan uzun süredir ilerlemiyor;
- `producer_behind` — producer'ın son yayını due saatin `max_hours_behind`tan fazla gerisinde;
- `inputs_unreadable` — girdi okunamıyor.

### 2. Sessizlik asla sağlıklı sayılmaz

Girdi okunamıyorsa bu kendi başına bir olaydır (`inputs_unreadable`), sessiz bir "ok" değil.
Okunamayan girdiden ilerleme çıkarımı yapılmaz ve değerlendirme orada kesilir. Bir izleyicinin
yapabileceği en kötü şey, doğrulamadığı sağlığı bildirmektir (MCP ADR-0006 §8).

### 3. Geç uyarı kesintiyi küçük göstermez

Ajan host uykudayken koşamaz; uyarı kesintinin başlangıcından çok sonra yüzeye çıkabilir. Bu
yüzden uyarı metni "az önce fark edildi" demez: **gözlenen boşluğu** ve **son bilinen sağlıklı
anı** taşır. Metin ayrıca yerel izlemenin bu sınırını açıkça söyler.

Bu, alarmın uykuyu çözmediğini de kabul etmektir: uyku sürerse uyarı da gecikir. Alarm
uykuyu değil, **sessizliği** çözer.

### 4. Tekrar uyarı outbox idempotency + escalation kovalarıyla engellenir

Uyarı, saatlik kartın kullandığı **aynı outbox**'a `runtime_health_alert` türüyle yazılır;
paralel bir teslimat yolu, ayrı secret veya yeni kanal yoktur. Mevcut pump teslim eder.

Kesinti kimliği `(koşul, son bilinen sağlıklı an)` çiftidir. Uyarı yalnız yapılandırılmış
escalation eşikleri (varsayılan 2/6/12/24/48 saat) **aşıldığında** yenilenir; aradaki koşular
aynı `signal_id` ve aynı gövdeyi üretir, dolayısıyla idempotenttir.

Bu, gövdenin yalnız `signal_id`'ye giren alanlardan türemesini zorunlu kılar: outbox aynı
anahtarı farklı gövdeyle **reddeder** (7 Ağustos'ta gözlenen `ValueError` tam da budur).
`now` bu nedenle metne bilinçli olarak girmez.

### 5. Toparlanma bildirimi durum dosyasından türetilir

Koşul temizlendiğinde bir "ilerleme geri döndü" bildirimi çıkar. Bunun için outbox taranmaz;
her koşuda zaten atomik yazılan durum dosyası doğal state taşıyıcısıdır. Dosya kaybolursa
toparlanma bildirimi atlanır — kaçırılan bir "her şey yolunda", kaçırılan bir kesintiden çok
daha ucuz bir hatadır.

### 6. İzleyici üretim kararına dokunmaz

Araç yalnız yerel durumu okur (ağa çıkmaz), yön üretmez, sonuç okumaz, Registry'ye yazmaz.
Uyarı metninde yatırım tavsiyesi dili yasaktır ve bu testle zorlanır. Eksik saatler bu
paketle de **doldurulmaz**.

### 7. Eşikler işletim eşiğidir

`config/runtime_health_alert.yaml` operasyonel eşikleri taşır. "Eşikler göreli yüzdelik olur"
kuralı ölçüm/tetik eşiklerini bağlar; burada ölçülen piyasa değil, kendi sürecimizin
ilerleyip ilerlemediğidir. Config fail-loud doğrulanır.

## Kanıt

Tamamen sentetik testler (`tests/test_runtime_health_alert.py`; ağ, `user_data/` veya canlı
runtime state bağımlılığı yoktur):

- `test_permanently_degraded_coverage_alone_is_not_an_outage` ve
  `test_a_single_missed_hour_is_below_the_stall_threshold` — gürültü üretilmediğini gösterir.
- `test_the_real_17_hour_outage_would_have_been_caught` — gerçek olayın verisiyle
  (`2026-08-09T22:00Z` → due `15:00`) 17 saatlik boşluk ve 12 saatlik kova saptanır.
- `test_unreadable_input_is_an_incident_never_a_silent_ok`.
- `test_same_incident_and_bucket_render_byte_identically` ve
  `test_escalation_produces_a_new_alert_only_when_a_step_is_crossed` — alarm fırtınası yok.
- `test_cli_enqueues_once_and_stays_idempotent_on_reruns`,
  `test_cli_emits_a_recovery_notice_once_progress_returns`.
- `test_alert_body_carries_no_direction_or_trading_language` — yön/tavsiye dili yok, gerçek
  boşluk metinde.

## Sonuçlar ve sınırlar

Bu paket kesintinin **görünmesini** sağlar; kesintiyi **önlemez**. Bilinçli olarak hâlâ yok:

- **Uzak bildirim.** Uyarı yerel outbox'a yazılır ve mevcut pump (runtime'da console modunda)
  teslim eder. Makine kapalıysa kimse uyanmaz; Telegram operasyon kanalı Faz 3 işidir.
- **Uyku çözümü.** Host uykudayken ajan da koşmaz. Alarm sessizliği çözer, uykuyu çözmez.
- **Kaçan saatlerin telafisi.** Backfill yapılmaz; eksik saatler blocker olarak kalır.

Bu ADR kapsama, kalibrasyon veya yön konusunda hiçbir iddia taşımaz.
