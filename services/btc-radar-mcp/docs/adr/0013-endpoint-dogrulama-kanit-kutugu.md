# ADR-0013 — Yeşil CI doğrulama değildir: kanıt kütüğü

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0001 (smoke scripti), **ADR-0009 (bu ADR onun açık bıraktığı maddeyi kapatır)**,
  ADR-0007, SPEC §6.3, SPEC §8 risk 3

## Bağlam

ADR-0009 coğrafi engeli sözleşme kırılmasından ayırdı ve günlük `MCP Smoke` iş akışını
kalıcı kırmızıdan kurtardı. Doğru karardı; ama kendi sonuç bölümünde bir madde açık bıraktı:

> "Kanıt, engellenmemiş bir ağdan `make smoke` ile üretilir."

**Bu kanıt bugüne kadar bir kez bile üretilmedi.** 11 Ağustos 2026'daki ölçüm:

```
Toplam: 24 kontrol, 10 OK, 0 zorunlu FAIL, 14 blocked_in_environment
```

Yani günlük iş akışı **her gün `success` diyor** ve o yeşil rozetin arkasında ürünün fiilen
bağlı olduğu 14 uç — bütün Binance türev/spot zinciri ve Bybit — **hiç doğrulanmıyor**.
Ayrıca `--skip-bitcoin-data` yüzünden bitcoin-data.com'un 4 kontrolü de CI'da hiç koşmuyor.
Rozet 28 kontrolün 10'unu kapsıyor, ama 28'ini kapsıyormuş gibi okunuyor.

Bu, bu depoda tekrar eden bir kusur sınıfıdır: **her koşuda aynı değeri veren bir gösterge
hiçbir şeyi korumaz.** `git_dirty` hiçbir zaman `False` olamıyordu (Signal ADR-0044),
coverage `status` kalıcı olarak `degraded`dı, `healthy` hiçbir zaman `True` olamıyordu
(ADR-0011, ADR-0012). Buradaki biçimi tersidir — gösterge kalıcı olarak **yeşil** ve
kapsamı sessizce dar.

Somut zarar, ADR-0009 §3'ün uyardığı yerde görünür: `binance_forceorders_removed` kontrolü
`expect_failure=True` ile çalışır. Engelli ağdan bakan biri onu asla doğru sebeple
doğrulayamaz. 11 Ağustos'ta engellenmemiş ağdan koşulduğunda uç **404** döndü — "bu uç
kaldırılmıştır" varsayımı ilk kez gerçekten doğrulandı.

Bunu bir doküman disiplini olarak bırakmak reddedildi: "ayda bir yerelden koş" diyen bir
runbook satırı, koşulup koşulmadığı ölçülemediği için ilk kesintide çürür.

## Kararlar

### 1. Kanıt kütüğü: engelsiz koşuların tarihli kaydı

`docs/endpoint-verification-log.md`, engellenmemiş bir ağdan koşulmuş doğrulamaların
append-only kaydıdır. Her girdi tarih, commit, kapsam ve kontrol başına HTTP durumu taşır.
Kütük "bu zincir en son ne zaman ve hangi kod sürümünde gerçekten doğrulandı" sorusunu
cevaplanabilir kılar; bugün bu soru cevapsızdır.

### 2. Kapı kapalıdır: engelli ya da kırık koşu kanıt değildir

`--record` yalnız hiçbir kontrolü `blocked` ve hiçbir zorunlu kontrolü `fail` olmayan
koşuyu yazar; aksi hâlde `EvidenceRefused` ile reddeder ve **kütüğe dokunmaz**.

Kısmi kayda izin vermek kütüğün tek işlevini yok ederdi: okuyucu, doğrulanmamış bir zinciri
doğrulanmış sanardı. CI'nın her gün ürettiği koşu tam olarak bu reddedilen türdür — test
bunu adıyla korur.

`warn` (bilgilendirici kontrol düşmesi) kaydı engellemez, ama girdide **adıyla listelenir**;
aksi hâlde girdi "hepsi doğrulandı" diye okunurdu. Bu, ADR-0009 §4'teki "ne doğrulanmadığını
adıyla söyle" kuralının kütüğe uygulanmış hâlidir.

### 3. Kapsam girdide yazılıdır

`--skip-bitcoin-data` ile koşulan bir doğrulama kütüğe "bitcoin-data hariç" olarak geçer.
Dar kapsamlı bir koşunun tam kapsam gibi okunması, düzeltilmek istenen kusurun aynısıdır.

### 4. Ham piyasa verisi kütüğe girmez

JSON raporun `sample` alanı yanıt gövdelerini taşır; kütük yalnız kontrol kimliği, HTTP
durumu ve SPEC referansı yazar (platform CLAUDE.md kural 2). Test bunu açıkça korur.

### 5. `make smoke-evidence`

Hedef `--fail-on-blocked --record` ile koşar. Engelli bir ağdan çalıştırılırsa çıkış kodu 2
olur ve hiçbir şey kaydedilmez — yanlış ağdan üretilmiş bir "kanıt" sessizce kütüğe
giremez. `make smoke` (CI güvenli varsayılan) değişmeden kalır.

## Kanıt

Sentetik testler (`tests/test_verify_endpoints.py`, ağa çıkmadan): engelli koşu reddedilir ·
zorunlu kontrolü düşmüş koşu reddedilir · reddedilen koşu kütükte iz bırakmaz · temiz koşu
kapsamıyla birlikte kaydedilir · `warn` görünür kalır · `sample` içeriği kütüğe sızmaz ·
ikinci kayıt birincisini bit-bit korur ve başlık tekrarlanmaz.

Canlı doğrulama (11 Ağustos 2026, engellenmemiş ağ): **28 kontrol, 28 OK, 0 zorunlu FAIL,
0 blocked_in_environment**, `--fail-on-blocked` ile çıkış kodu 0. Kütüğün ilk girdisi budur.
Aynı gün GitHub-hosted runner'dan koşan iş akışı 24 kontrolün 14'ünü doğrulayamamıştı.

## Sonuçlar ve sınırlar

Bilinçli olarak **hâlâ yok**:

- **Binance zincirinin CI'da doğrulanması.** Bu ADR de engeli kaldırmaz; ADR-0009'un proxy /
  self-hosted runner reddi geçerlidir. Değişen tek şey, engelsiz kanıtın artık **ölçülebilir
  ve tarihli** olmasıdır.
- **Kayıt cadence'ının zorlanması.** Kütük eskirse bunu kimse bildirmez; "en son doğrulama N
  günden eski" alarmı yazılmadı. Alarm altyapısı Faz 3 işidir (ADR-0006) ve bu kütük ona
  ölçülebilir girdi verir — bugün o girdi bile yoktu.
- **Koşunun kirli ağaçtan üretilip üretilmediğinin kaydı.** Girdi commit SHA'sı taşır,
  `git_dirty` taşımaz; smoke scripti çalışma ağacına değil canlı uçlara bakar.
