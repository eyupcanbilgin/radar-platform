# ADR-0053 — Tekrar eden özdeş hata geçici değildir; alarm sebebi adıyla söyler

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** **ADR-0051 (bu ADR onun açık bıraktığı maddeyi kapatır)**, ADR-0042
  (kesinti dedektörü), MCP ADR-0006 (heartbeat), MCP ADR-0012

## Bağlam

ADR-0051, bugünkü kesintinin kök nedenini kaydetti — kurulu paket ile config'in sürüm
ayrışması — ve sonuç bölümünde bir maddeyi bilinçli olarak açık bıraktı:

> "**Sürüm ayrışmasının makine tarafından engellenmesi.** Runbook artık adımı yazıyor ama
> kurulu paket ile checkout SHA'sını karşılaştıran bir kapı yok."

O maddeye dönerken tasarımın ilk hâli yanlış çıktı. "Başlangıçta config'i doğrula ve çök"
düşünülmüştü; **işe yaramazdı**: daemon zaten çalışıyordu, ayrışma checkout güncellenince
*sonradan* doğdu. Başlangıç kontrolü o anı hiç görmezdi.

Gerçek boşluk başka yerdeydi. `ProducerScheduler._run` her hatayı yutar:

```python
except Exception as error:  # tek bir hata toplayıcıyı öldürmemeli
```

Bu **geçici** hata için doğru davranıştır — ağ zaman aşımı toplayıcıyı öldürmemeli. Ama şema
hatası **kalıcıdır**: 6798 kez denemek onu düzeltmez. Producer stdout kütüğünde tam olarak
6798 özdeş `ValidationError` birikti ve hiçbiri teşhis olarak yüzeye çıkmadı.

`producer_behind` o gün yalnız **aralıklı** ateşledi, çünkü producer üç saatte bir yayın
yapabiliyordu; ateşlediğinde de yalnız "geride" dedi. Sebep — hangi görev, hangi hata —
heartbeat'in `detail` alanında duruyordu ve **hiçbir alarma ulaşmıyordu**. Operatörün
teşhise ulaşma yolu stdout kazmaktı.

## Kararlar

### 1. Yeni koşul: `producer_failing`

Producer heartbeat'inde bir görev `min_consecutive_failures` (varsayılan **3**) kez üst üste
hata almışsa olay üretilir. Eşik gürültüyü dışarıda tutar: tek tük ağ hatası kesinti değildir.

### 2. Alarm sebebi adıyla söyler

Olay metni görevi, hata tipini, kesilmiş hata mesajını ve **ardışık tekrar sayısını** taşır;
ayrıca operatöre ilk bakılacak yeri söyler:

> "producer 'collect' görevi 47 kez ÜST ÜSTE aynı hatayı aldı: ValidationError — … Tekrar
> eden özdeş hata geçici değildir; kurulu paket ile checkout arasındaki sürüm ayrışması ilk
> bakılacak yerdir."

Bu, bugün üç saat süren teşhisi tek satıra indirir.

### 3. Kaynak heartbeat'tir ve seri son başarıda kapanır

Sayım `detail` sütununu okuyan salt-okunur bir sorgudan gelir. Bir görevin serisi, o görevin
**son başarısında** kapanır; daha eski hatalar sayıya girmez. Birden çok görev düşüyorsa
serisi en uzun olan raporlanır.

### 4. Olay kesintinin BAŞLANGICINA çapalanır

`since_utc`, serideki **en eski** hatanın anıdır. Geç fark edilen bir kesinti süresini
olduğundan kısa göstermemelidir — ADR-0042'nin "geç alarm kesintiyi küçümsemesin" kuralının
aynısı.

### 5. Toplayıcı döngüsü DEĞİŞMEDİ

Producer hâlâ hata alınca ölmez ve çıkış kodu döndürmez. Bilinçli: çöküp launchd'ye yeniden
başlatmayı bırakmak, kalıcı hatada sıcak yeniden-başlatma döngüsü üretirdi (ADR-0037'nin
kaçındığı desen). Değişen tek şey **görünürlüktür**.

## Kanıt

Sentetik testler (`tests/test_runtime_health_alert.py`, ağa çıkılmaz): tekrar eden şema
hatası olay üretir ve metni sayıyı, hata tipini, `sampling_mode`'u ve "sürüm ayrışması"
yönlendirmesini taşır · kısa seri (2) olay değildir · eşikteki seri (3) ateşler · seri yoksa
olay yoktur · olay kesintinin başlangıcına çapalanır (`gap_hours` 6, `since` 09:00) · okuyucu
yalnız **güncel** seriyi sayar (başarıdan öncesi girmez) · birkaç görev düşüyorsa en kötüsü
raporlanır · hatasız heartbeat `None` döner.

Test fixture'ı gerçek `HeartbeatStore` şemasıyla hizalandı: `detail` ve `id` sütunları
olmadan kesintinin sebebi zaten okunamıyordu — eksik olan bilgi tam da buydu.

## Sonuçlar ve sınırlar

Bilinçli olarak **hâlâ yok**:

- **Otomatik onarım.** Alarm sebebi söyler; paketi kimse yeniden kurmaz. Otomatik yeniden
  kurulum, çalışan bir runtime'ın kodunu habersiz değiştirmek olurdu.
- **Kurulu paket ↔ checkout SHA karşılaştırması.** Doğrudan sürüm kıyası hâlâ yok; bu koşul
  ayrışmayı **sonucundan** yakalar, kendisinden değil. Doğrudan kıyas paketin kurulum anında
  commit gömmesini gerektirir ve ayrı bir karardır.
- **Uyarının okunması.** Teslimat `console` modundadır. Bu ADR bir alarmı daha üretir ve o da
  aynı yerde bekler; kanal kararı ürün sahibindedir (ADR-0049).
