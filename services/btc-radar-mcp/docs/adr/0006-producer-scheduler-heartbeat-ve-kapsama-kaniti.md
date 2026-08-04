# ADR 0006 — Producer scheduler, heartbeat ve kesintisiz işletim kanıtı

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0005, Signal ADR-0009, Hedefe Geliştirme Planı Faz 1

## Bağlam

ADR-0005 geçmiş birikimini ve kırılganlık kapısını getirdi ama `collect` ile `publish` hâlâ
elle çağrılıyordu. Saatlik OI ucu ~30 gün saklıyor: toplayıcı durursa o pencerenin ötesindeki
geçmiş **geri getirilemez**. Dolayısıyla sürekliliğin kendisi bir veri gereksinimidir.

İkinci ve daha ince sorun: "kesintisiz çalıştı" iddiasını neyin kanıtladığı. Bir süreç
"ayaktaydım" diyebilir; bu, serinin tam olduğunu göstermez. Boş bir saat üç farklı şey
olabilir — piyasa sakindi, uç hata verdi, süreç ölüydü — ve PIT deposu tek başına bunları
ayırt edemez.

## Kararlar

### 1. Tek döngü, iki ritim

`ProducerScheduler` saat içinde `collect` (varsayılan 300 sn), saat kapandıktan sonra bir kez
`publish` çalıştırır. Toplama, aynı tick içinde yayından **önce** yapılır ki yayınlanacak
saatin verisi depoda olsun.

Yayın grace'i 45 sn'dir ve bu **bilinçli olarak** radar-signal'in 90 sn'lik okuma grace'inden
küçüktür: tüketici dosyayı aradığında artifact yerinde olmalıdır.

### 2. Hata döngüyü durdurmaz, kayda geçer

Geçici bir HTTP hatası daemon'u öldürseydi, bileşenin var olma sebebi olan deliği garanti
ederdi. Başarısız görev `error` olarak kaydedilir, döngü devam eder.

Tick içinde retry **yoktur**; bir sonraki tick zaten retry'dır. Toplama aralığı son
*denemeden* ölçülür — son *başarıdan* ölçülseydi, sürekli hata veren bir uç döngüyü saniyede
onlarca isteğe çevirir ve IP banına giden yol olurdu.

### 3. Heartbeat: sürecin koştuğunun kanıtı

`HeartbeatStore` append-only bir koşu kütüğüdür: görev, durum, başlangıç/bitiş, süre, karar
saati ve ayrıntı. Sonraki başarı, önceki hatayı **silmez**; kesinti kaydı kalıcıdır.
`skipped` durumu hata sayacına girmez: atlamak bilinçli bir karardır, arıza değil.

### 4. Kapsama: verinin tam olduğunun kanıtı

`core/coverage` toplanan serinin kendisini ölçer: beklenen örneklem, gözlenen örneklem, en
uzun boşluk ve boşluğun **nerede** olduğu. Eşikler burada uydurulmaz; `signal_rules.yaml`
içindeki feature spec'lerinden gelir, böylece operatör raporu ile feature blocker'ı "boşluk"
kelimesine aynı anlamı verir.

**Uptime kapsama değildir.** Bir görev başarıyla koşup uç kısa sayfa döndürmüşse heartbeat
"ok" der, kapsama "delik var" der. İkisi birlikte kanıttır; ayrı ayrı değil.

### 5. Yakalama sınırlıdır ve etiketlidir

Kesintiden sonra scheduler en fazla `--catch-up-hours` kadar kaçırılmış saati yayınlar; her
biri `catch_up` etiketi taşır, böylece geç üretilmiş bir artifact canlı işletim sanılmaz.
Sınırın ötesi **sessizce düşürülmez**: `skipped` koşusu olarak kaç saatin ve hangi aralığın
dışarıda kaldığını yazar. Sessiz kırpma, "her şeyi kapsadık" gibi okunur.

İlk koşu geçmişi yeniden yayınlamaz. Hangi geçmişin yayınlanacağı bir karardır; scheduler onu
kendiliğinden vermez.

### 6. Tek örnek koruması, otomatik temizlik olmadan

`--lock-file` ile ikinci daemon başlatılamaz. Bayat kilit **otomatik silinmez**: dışarıdan
"o PID ölmüş" demek bir tahmindir ve yanlış tahmin, tam da engellemek istediğimiz ikinci
toplayıcıyı başlatır. Hata mesajı sahibin PID'ini ve kilit zamanını verir; kararı operatör
verir. (Canlı doğrulamada süreç sert öldürüldü, kilit kaldı ve ikinci başlatma reddedildi.)

### 7. Tek-tick modu birinci sınıftır

`run` varsayılan olarak **tek geçiş** yapar; `--daemon` isteğe bağlıdır. Windows'ta doğru
süpervizör bizim döngümüz değil, işletim sistemidir: Task Scheduler her dakika `run`
çağırırsa çöken süreç bir sonraki dakikada kendiliğinden geri gelir ve kilit dosyası ile
çakışma önlenir. Daemon modu servis yöneticisi olan ortamlar (systemd/nssm) içindir.

### 8. Sağlık yüzeyi ve hata biçimi

`get_health` yerel PIT ve heartbeat depolarını okuyup görev özeti + 7 günlük kapsama döndürür
(ağ çağrısı yok). Depolar tanımlı değilse `not_configured`, okunamıyorsa `unreadable` der —
bir sağlık aracının yapabileceği en kötü şey, bilmediği için "sağlıklı" demektir.

CLI hataları ham traceback değil, `stderr`'e makine-okunur JSON ve çıkış kodu 2'dir.

## Sonuçlar ve sınırlar

Canlı doğrulama (4 Ağustos 2026): daemon 15 sn aralıkla üç toplama yaptı, aynı saati ikinci
kez yayınlamadı; `status` 7 günlük pencerede iki metrik için de `coverage_ratio=1.0`,
tolerans içi boşluk ve `hours_behind=0` raporladı.

Bilinçli olarak **hâlâ yok**:

- **Alarm/bildirim.** Kesinti kütüğe yazılır; kimseyi uyandırmaz. Telegram operasyon kanalı
  Faz 3 işidir.
- **Uzak izleme.** Heartbeat yereldir; makine kapalıysa kimse bilmez.
- **Zarif durdurma garantisi (Windows).** SIGINT/SIGTERM işlenir ve testlidir, ama Windows'ta
  sert öldürme kilit dosyasını bırakır; temizlik operatörün kararıdır (madde 6).
- **Tüketim doğrulaması.** Scheduler context'i yayınlar; radar-signal'in onu gerçekten
  okuduğunu doğrulamaz. Bu, iki servisi kapsayan ayrı bir uçtan uca kontroldür.
- **Varsayılan yakalama penceresi 0'dır.** Kesintiden sonra geçmiş saatlerin yayınlanması
  açık bir tercihtir; sessizce açık gelmez.

Bu paket "toplama sürekli çalışabilir ve sürekliliği kanıtlanabilir" demektir; "sistem
izleniyor ve arıza bildiriliyor" demek değildir.
