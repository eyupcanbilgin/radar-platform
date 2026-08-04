# ADR 0009 — Coğrafi engel, sözleşme kırılmasından ayrı bir durumdur

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0001 (smoke scripti), SPEC §2.1, SPEC §8 risk 3, `.github/workflows/mcp-smoke.yml`

## Bağlam

Günlük `MCP Smoke` iş akışı her koşuda kırmızıydı. Koşu 30894903581 kütüklerinde sebep
görünüyor: Binance uçları GitHub-hosted runner'a `403` ile ve şu gövdeyle yanıt veriyor —
"The Amazon CloudFront distribution is configured to block access from your country."
Runner bölgesi Binance tarafında coğrafi olarak engellidir. Bu bir kod kusuru değildir,
mevcut çalışmadan da eskidir; ne yeniden deneme ne de scriptte bir düzeltme kaldırır.

Script bu yanıtı "HTTP 200 değil → FAIL" kovasına atıyordu. Sonuç iki ayrı zarardır:

1. **Kalıcı kırmızı = gürültü.** Her gün başarısız olan bir kontrol, bir gün gerçekten
   kırıldığında kimseyi uyandırmaz. Sinyal değeri sıfırdır.
2. **Yanlış etiket.** "Binance OI uç sözleşmesi kırıldı" ile "bu ağdan Binance'e
   erişilemiyor" farklı olaylardır ve farklı eylem gerektirir. Birincisi SPEC güncellemesi,
   ikincisi ağ/koşum ortamı kararıdır.

Daha ince bir zarar da vardı: `binance_forceorders_removed` kontrolü `expect_failure=True`
ile çalışır, yani ≥400 gördüğünde "uç gerçekten kaldırılmış" diye **yeşil** yanar. Coğrafi
403 bu kontrolü doğru sebeple değil, yanlış sebeple geçiriyordu — engelli bir ağdan bakan
biri, uç geri gelse bile bunu asla göremezdi.

Değerlendirilen ikinci seçenek, iş akışını bölmekti: fixture/sözleşme kontrolleri
GitHub runner'da, canlı Binance kontrolleri self-hosted runner'da. Reddedildi; elimizde
self-hosted runner yok ve olmayan bir runner'a taşımak, kontrolü "çalışıyor" gibi
göstererek tamamen silmek olurdu. Ayrıca engelin *ne olduğunu* söyleme sorunu, kontrolü
başka bir makineye taşımakla çözülmez: engellenmiş ağdan koşan geliştirici aynı yanlış
etiketi yerelde görmeye devam ederdi.

## Kararlar

### 1. Üçüncü durum: `blocked_in_environment`

`Result` artık `blocked` alanı taşır ve `state` özelliği dört değerden birini döndürür:
`ok`, `fail` (zorunlu kontrol düştü), `warn` (bilgilendirici kontrol düştü), `blocked`.
Bu, `required`/informational ayrımının zaten var olan mantığının doğal devamıdır: rapor
"geçti mi?" değil, "ne öğrendik?" sorusuna cevap verir.

`blocked` bir başarı değildir. `ok=False` kalır — çünkü sözleşme **doğrulanmamıştır**.
Sadece "ihlal edildi" de denmez.

### 2. Engel için iki kanıt birden aranır

`geo_block_reason()` yalnızca **hem** statü (`403`/`451`) **hem de** gövde işareti
eşleşirse engel der. İşaretler: CloudFront'un ülke engeli metni ve Binance'in kendi
`"service unavailable from a restricted location"` yanıtı.

Tek başına 403'ü engel saymak en tehlikeli yol olurdu: imza hatası, kaldırılmış uç ve WAF
reddi de 403'tür. Onları "engellendi" diye yutmak, tam olarak kaçırmak istemediğimiz
sözleşme kırılmasını gizlerdi.

### 3. Engel kontrolü `expect_failure`'dan önce gelir

Sıralama bilinçlidir. Coğrafi 403, "bu uç kaldırılmış" varsayımının kanıtı sayılamaz;
engelli bir ağdan hiçbir uç hakkında "kaldırılmış" denemez. `binance_forceorders_removed`
artık engel altında `blocked` döner, `ok` değil.

### 4. Rapor ne doğrulanmadığını adıyla söyler

Özet satırı üç sayıyı ayrı verir (`OK`, `zorunlu FAIL`, `blocked_in_environment`) ve engel
varsa altına engellenen kontrollerin **listesi** yazılır: "bu koşu onlar için kanıt
üretmemiştir". Sessiz yutma, "hepsini doğruladık" gibi okunur — ADR-0006 §5'teki sessiz
kırpma yasağının aynısı.

### 5. Çıkış kodu: engel 0, sözleşme kırılması 1, istenirse engel 2

Varsayılan olarak engellenmiş-ama-erişilebilir uçlar çıkış kodunu bozmaz; zorunlu bir
sözleşme kontrolü düşerse kod 1'dir. `--fail-on-blocked` bayrağı engeli de başarısızlık
sayar (kod 2) ve **engellenmemiş bir ağdan** koşarken kullanılır: orada engel gerçekten
bir haberdir. Sözleşme kırılması engeli ezer — ikisi birden varsa kod 1'dir, çünkü asıl
haber odur.

### 6. CI: engel beklenen durumdur, ama görünürdür

`mcp-smoke.yml` script çıktısını `$GITHUB_STEP_SUMMARY`'ye yazar ve JSON raporu artifact
olarak yükler. Böylece engelin kapsamı, kütükleri açmadan koşu sayfasından görülür ve
"engel bugün büyüdü mü?" sorusu cevaplanabilir olur.

## Sonuçlar ve sınırlar

Bilinçli olarak **hâlâ yok**:

- **Binance zincirinin CI'da doğrulanması.** Bu ADR engeli etiketler, kaldırmaz. Günlük
  koşu Binance uçları için kanıt üretmez ve bunu açıkça yazar. Kanıt, engellenmemiş bir
  ağdan `make smoke` ile üretilir. Proxy ya da self-hosted runner ayrı bir karardır;
  ikisi de yeni bir bağımlılık ve yeni bir güven varsayımı getirir.
- **Ağ katmanında kesilen bağlantıların sınıflandırılması.** Engel HTTP yanıtı yerine
  bağlantı sıfırlaması olarak gelirse `httpx.HTTPError` yoluna düşer ve `fail` sayılır.
  Ayırt edici gövde işareti olmadan bunu "engel" demek tahmin olurdu.
- **`expect_failure` + ağ hatası boşluğu.** Ağ seviyesinde kesilen bir istek,
  `binance_forceorders_removed` kontrolünü hâlâ "kaldırılmış" varsayımıyla uyumlu sayar.
  Bu, engel sınıflandırmasından önce de böyleydi; madde açık kalır.
- **Engelin kalıcılığının izlenmesi.** Engel bir gün kalkarsa kontroller kendiliğinden
  yeşile döner, ama bunu kimse bildirmez. Alarm hâlâ Faz 3 işidir (ADR-0006).

Bu paket "coğrafi engel artık sözleşme kırılması gibi görünmüyor ve neyin doğrulanmadığı
yazılı" demektir; "Binance zinciri CI'da doğrulanıyor" demek değildir.
