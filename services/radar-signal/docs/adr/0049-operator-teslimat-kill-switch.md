# ADR-0049 — Operatör teslimat kill-switch'i: durdurur, kaybetmez

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0011, ADR-0042, ADR-0048, Hedefe Geliştirme Planı Faz 3

## Bağlam

Bugüne kadar teslimatı durdurmanın **tek** yolu pump daemon'unu öldürmekti. Bu, iş için kötü
bir alettir:

- kuyrukta bekleyen mesajların yeniden denenmesini de durdurur;
- teslimatın **neden** durduğuna dair hiçbir kayıt bırakmaz;
- tam da bir şeyler ters giderken terminal başında olmayı gerektirir.

Bu eksik, ADR-0048 ile kırılganlık uyarı kartı outbox hattına bağlandığı anda taşıyıcı hâle
geldi: kart kapısı bir gün açıldığında, kart yanlış davranırsa operatörün tek adımda durdurup
sonra düşünebilmesi gerekir.

Planın Faz 3 maddesi bunu zaten istiyordu: *"…manuel pause kill-switch'lerini ekle."*

## Kararlar

### 1. Duraklatma tutar, atmaz

Anahtar etkinken mesajlar outbox'ta `PENDING` kalır ve anahtar kalkınca gönderilir. Mesaj
düşüren bir kill-switch, operatörü onu kullanmaktan çekindirir — ki bu, aracın var olma
sebebini ortadan kaldırır.

### 2. Varlık sinyaldir

Anahtar bir **dosyadır**; varsa teslimat durur. İçerik ayrıştırılmaz, truthy/falsy
yorumlanmaz. İçeriğe bakan bir tasarımda dosyaya `false` yazmak teslimatı sürdürürdü — bir
durdurma kontrolünde bu kabul edilemez bir sürprizdir ve test bu tuzağı açıkça korur.

### 3. Belirsizlik DURMA yönünde çözülür

Dosya var ama okunamıyorsa duraklatma yine geçerlidir; yalnız gerekçe bilinmiyordur. Varlığı
saptamak bile başarısız olursa (OSError) yine durulur. Bir durdurma kontrolünde bilinmezlik,
göndermeye değil durmaya çıkmalıdır.

### 4. Gerekçe anahtarla birlikte taşınır

Operatörün dosyaya yazdığı metin pump log satırına geçer. "Neden hiçbir şey gitmiyor?"
sorusu hafızadan değil **logdan** cevaplanabilmelidir. Metin kırpılır ki kill-switch dosyasına
kazara yazılan büyük bir çıktı logu boğmasın.

### 5. Durum değişimi bir kez loglanır

Her turda "duraklatıldı" yazmak logu boğar ve gerçek olayları görünmez kılar; yalnız
duraklama ve devam etme anları loglanır.

### 6. Anahtar opt-in'dir

`--pause-file` verilmezse davranış birebir eskisidir. Runtime plist'inde açıkça
`state/signal/delivery.pause` olarak bağlanmıştır; test bunu doğrular.

## Kanıt

Sentetik testler (`tests/test_delivery_pause.py`; yalnız `tmp_path` dosyaları): anahtar
verilmeyince duraklatma yok · dosya yoksa çalışır · **varlık tek başına durdurur** · içerik
gerekçe olarak taşınır · **`false` yazan dosya da durdurur** · okunamayan dosya duraklatmaya
çözülür · uzun gerekçe kırpılır · anahtar kalkınca devam eder.

Uçtan uca canlı doğrulama (11 Ağustos 2026, geçici outbox; canlı state'e dokunulmadan):

1. anahtar yokken mesaj gönderildi (`sent: 1`);
2. anahtar konunca pump `pompa DURAKLATILDI (kart metni yanlış — operatör durdurdu)` yazdı ve
   mesaj outbox'ta `PENDING` kaldı — **kaybolmadı**;
3. anahtar kaldırılınca aynı mesaj gönderildi ve `SENT` oldu.

## Sonuçlar ve sınırlar

Operatörün artık teslimatı durdurmak için daemon öldürmesi gerekmiyor ve durdurma kararı
kayda geçiyor.

Bilinçli olarak hâlâ yok:

- **Otomatik kill-switch'ler.** Günlük/haftalık zarar, maksimum drawdown ve stale-data
  tetikleyicileri Faz 3'ün ayrı maddeleridir; bunlar pozisyon ve sonuç verisi ister,
  bugün ikisi de yoktur (`direction=null`, kart kapısı kapalı).
- **Uzaktan kontrol.** Anahtar yereldir; makine kapalıysa kimse durduramaz.
- **Üretimi durdurma.** Anahtar yalnız **teslimatı** durdurur; saatlik karar defteri ve
  forward gözlem kaydı çalışmaya devam eder. Kanıt toplamayı durdurmak ayrı ve daha ağır bir
  karardır.
