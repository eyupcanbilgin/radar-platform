<!-- Kaynak: Harici AI değerlendirmesi #2 (madde-bazlı rapor) · Alınma: 3 Ağustos 2026 · CR-002'nin kanıt kaynağı -->

Eyüpcan merhaba. RADAR SİSTEMİ v1.0 mimari dokümanını ve metodolojik yaklaşımını detaylıca inceledim. Bir QA / SDET gözüyle tasarlanmış, modülerliği, test edilebilirliği ve determinizmi merkeze alan **kurumsal/quant standartlarında** çok olgun bir mimari metni var karşımızda.

Özellikle canlı döngüde LLM kullanımının reddedilmesi, purged walk-forward + Deflated Sharpe kullanımı ve fail-closed yaklaşımı projenin sağlam temellere oturduğunu gösteriyor.

Bölüm 8'de talep ettiğin değerlendirmeleri, sorularının madde sırasına sadık kalarak, her biri için **Etkilenen Bileşen**, **İlke Uyumu/Çelişkisi** ve **Doğrulama Testi** detaylarıyla sunuyorum.

---

### 1. Mimari: İki-Proje Ayrımı ve HTTP Entegrasyonundaki Zayıf Noktalar (SPOF)

Sistem mimarisi (FastMCP / `btc-radar` $\leftrightarrow$ Freqtrade / `radar-signal`) veri sorumluluğu ile strateji yürütümünü mantıksal olarak çok iyi ayırmış. Ancak HTTP bağımlılığı üzerinden şu 3 kritik teknik risk ve SPOF öne çıkıyor:

#### A. Zaman Hizalama ve Veri Durum Uyuşmazlığı (Point-in-Time Disconnection)

* **Problem:** Freqtrade 15m mum kapandığı anda ($T_0$) stratejiyi çalıştırır. HTTP üzerinden `btc-radar` çağrıldığında, `btc-radar` o anki canlı REST API kaynaklarından (CoinGecko, Alternative.me, bitcoin-data vb.) anlık veri çekip skor üretecektir. Ancak on-chain veya sentiment kaynaklarının güncelleme periyotları (örn. 24 saatte bir, veya blok bazlı) mum kapanış anıyla senkronize değildir. Canlı ortamda $T_0$ anında hesaplanan rejim skoru ile backtest'te kullanılan veri uyuşmazlığı yaratır.
* **Etkilenen Bileşen:** `btc-radar` Normalizer/Feature katmanı, `radar-signal` HTTP Entegrasyonu.
* **İlke Uyumu:** *Determinizm* ilkesiyle çelişme riski taşır (Aynı mum kapanışına farklı milisaniyelerde gelen REST yanıtı farklı skor üretebilir).
* **Öneri & Test:** `btc-radar`, hesapladığı özellikleri ve rejim skorunu **mum bazlı timestamp anahtarıyla** önbelleğe almalı veya geçmişe dönük deterministic snapshot sunmalıdır (Point-in-Time Database).
* **Doğrulama Testi:** *Point-in-Time Determinism Test:* Aynı t anı için `btc-radar`'a 100 ardışık HTTP isteği atıldığında (cache ve TTL devreye girerek) %100 özdeş skor üretildiği doğrulanmalıdır.

#### B. Fail-Closed Durumunda Asimetrik Sinyal İptali ve Timeout Yönetimi

* **Problem:** 15m mum kapanışında `btc-radar` dış servis aşırı yükü veya HTTP timeout nedeniyle yanıt veremezse, sistem "fail-closed" gereği güven skorunu düşürüp işlemi engelleyecektir. Ancak bu durum, stratejinin saf teknik koşulunun (ör. S-0001) mükemmel olduğu anlarda sistemsel bir "sinyal kaçırma" (False Negative) yaratır.
* **Etkilenen Bileşen:** `Rationale Enricher` ve `radar-signal` filtre kapısı.
* **İlke Uyumu:** *Açıklanabilirlik* ile uyumlu fakat strateji başarımı istatistiğini bozar.
* **Öneri & Test:** `btc-radar` yanıt vermediğinde sinyal tamamen çöpe atılmak yerine Telegram'a **"TEKNİK SİNYAL TETİKLENDİ - REJİM BEYNİ ÇEVRİMDIŞI (İŞLEM ÖNERİLMEZ)"** etiketiyle düşmeli, dry-run defterinde ise bu durum ayrı bir bayrakla (flag) izlenmelidir.
* **Doğrulama Testi:** *Chaos / Timeout Injection Test:* Mock bir HTTP gecikmesi (örn. 5000ms delay) enjekte edildiğinde Freqtrade'in kilitlenmediği ve fallback mekanizmasının çalıştığı doğrulanmalıdır.

---

### 2. İstatistik: Backtest Protokolündeki Açıklar ve Sızıntı Kanalları

Purged walk-forward, Deflated Sharpe (DSR) ve A/B/C kıyası standartların çok üzerindedir. Ancak gözden kaçabilecek 3 ince sızıntı/önyargı kanalı bulunmaktadır:

#### A. On-Chain Verilerde "Sonradan Düzeltme" (Data Revision / Lookback Bias)

* **Problem:** STH-SOPR, CDD ve Borsa Netflow gibi on-chain metrikler, blok zincir re-org'ları veya borsaların adres kümeleme (clustering) algoritmalarını geriye dönük güncellemesi nedeniyle tarihi verilerde **değişir**. Tarihsel olarak çekilen bir CSV/API verisi, o gün $T_0$ anında borsa borsaya aktarıldığı anda bilinen veri değil, bugün bilinen "düzeltilmiş" veridir.
* **Etkilenen Bileşen:** Strateji Fabrikası / Backtest Protokolü.
* **İlke Uyumu:** *Test Edilebilirlik* ilkesini zedeler (Backtest performansı canlıdan daha iyi görünür).
* **Öneri & Test:** Backtest için kullanılan on-chain verilerin "restated/revised" değil, ilgili tarih/saat anındaki "raw/unrevised snapshot" olduğundan emin olunmalıdır.
* **Doğrulama Testi:** *Historical Revision Delta Test:* Bugün çekilen 3 ay önceki bir günün STH-SOPR verisi ile o gün canlı akıştan kaydedilmiş snapshot verisi karşılaştırılıp fark (delta) analiz edilmelidir.

#### B. Çoklu Hipotez İterasyon Sayısının DSR'a Yanlış Aktarılması

* **Problem:** Deflated Sharpe Ratio (DSR), yapılan toplam deneme sayısını ($N$) girdi olarak alır. Eğer 17 hipotez kartının her biri için 100 farklı parametre kombinasyonu denenmişse, $N = 1700$'dür. Yalnızca nihai elenen stratejinin hyperopt deneme sayısını DSR'a sokmak, over-fitting riskini hafife almaya sebep olur.
* **Etkilenen Bileşen:** Backtest Protokolü (DSR Hesaplayıcı).
* **İlke Uyumu:** *Test Edilebilirlik* ilkesiyle doğrudan ilgilidir.
* **Öneri & Test:** Araştırma sürecinde çalıştırılan **tüm başarısız/reddedilmiş hyperopt çalıştırmaları ve strateji varyasyonları** bir log veritabanında tutulmalı, DSR formülüne gerçek küresel deneme sayısı ($N_{total}$) verilmelidir.
* **Doğrulama Testi:** *Global Trial Audit:* Hyperopt çalışmasının total trial count değerinin DSR fonksiyonuna parametre olarak eksiksiz geçtiği unit test ile doğrulanmalıdır.

---

### 3. Sinyal Yaşam Döngüsü: İki-Hızlı Çıkış ve `--timeframe-detail 1m` Tutarlılığı

#### A. 5-Saniye Ticker Döngüsü ile Backtest (`--timeframe-detail 1m`) Arasındaki Çözünürlük Farkı

* **Problem:** Canlı/Dry-run ortamında stop-loss ve ROI kontrolleri ~5 saniyelik ticker döngüsünde yapılır. Backtest'te ise ulaşılabilecek en küçük mum içi çözünürlük 1 dakikadır (`--timeframe-detail 1m`). Aşırı volatil Anlarda (High Fragility) fiyat 5 saniye içinde stop seviyesini delip geri toplayabilir.
* **Canlıda:** 5 sn döngüsü stop'u tetikler.
* **Backtest'te:** 1m mumunun düşük seviyesi stop'a değmediyse veya kapanış yukarıdaysa stop tetiklenmez.
* **Etkilenen Bileşen:** `radar-signal` Pozisyon Defteri / Backtest Motoru.
* **İlke Uyumu:** *Test Edilebilirlik* (Canlı ile Backtest sapması yaratır).
* **Öneri & Test:** High Fragility ($\ge 60$) durumlarında 5 sn döngüsündeki stop hassasiyeti kaymayı (slippage) artırır. Backtest maliyet matrisindeki slippage değerini sabit tutmak yerine, rejim kırılganlığına bağlı olarak dinamik artırmak gerekir (örn. Standart 5 bps, Kırılganlık $\ge 60$ ise 25 bps slippage).
* **Doğrulama Testi:** *Intra-candle Execution Drift Test:* Dry-run sırasında tetiklenen stop/ROI zamanları ile 1m mum verisi üst üste bindirilerek "1m altı" tetiklemelerin oranı ve kârlılığa etkisi raporlanmalıdır.

#### B. İnsan Faktörünün Asenkronize Çıkış Riski

* **Problem:** Dokümanda *"fikrim değişti mum bekler, canım yanıyor beklemez"* ilkesiyle stop/ROI'nin 5 saniyelik döngüde otomatik izlendiği belirtilmiş. Ancak sistem **emir göndermediği** için, kullanıcının Telegram mesajını görüp manuel stop koyması en iyi ihtimalle 10-30 saniye sürer. Bu durumda dry-run defteri ile kullanıcının gerçek defteri ayrışacaktır.
* **Etkilenen Bileşen:** Karar Günlüğü / Kullanıcı Defteri.
* **İlke Uyumu:** Bölüm 7.1'deki itirafla uyumlu, ancak ölçülmesi gerekir.

---

### 4. Rejim Skorlaması: Ağırlıklı Skor Formülünün Zayıflıkları ($d \cdot q \cdot f \cdot u$)

Formül ($Direction = 50 \cdot \frac{\sum w \cdot d \cdot q \cdot f \cdot u}{\sum w \cdot q \cdot f \cdot u}$) matematiksel olarak temiz ve sezgiseldir. Ancak finansal zaman serilerinde şu iki kritik zayıflığa sahiptir:

#### A. Doğrusallık Varsayımı ve Non-Linear (Kritik) Etkileşimlerin Kaçırılması

* **Problem:** Metriklerin bağımsız toplanması (Linear Weighted Sum), extreme kombinasyonları yumuşatır (dampening effect).
* *Örnek:* Spot Premium nötr ($d=0$), SOPR nötr ($d=0$) ama Funding Rate aşırı negatif ($d=-2$) ve OI rekor seviyede ($r=2$). Lineer toplamda bu durum "Hafif Büyüklükte Nötr" çıkar. Oysa bu kombinasyon matematiksel olarak bir **Short Squeeze** patlamasıdır.
* **Etkilenen Bileşen:** `btc-radar` Scoring Engine.
* **İlke Uyumu:** *Determinizm* ile uyumlu fakat *Açıklanabilirlik* açısından yanıltıcı olabilir.
* **Öneri & Test:** Lineer ağırlıklı toplama ek olarak bir **"Hard Override / Circuit Breaker" (Kural Ağacı)** katmanı eklenmelidir. Belirli metrik bileşimleri oluştuğunda (örn. $OI_{z-score} > 2.5$ AND $Funding_{percentile} < 5$), lineer skor ne olursa olsun rejim etiketi doğrudan `Sıkışmalı Nötr` veya `Sıkışmalı Risk-On` olarak ezilmelidir (Override).
* **Doğrulama Testi:** *Non-Linear Regime Matrix Test:* Tarihteki bilinen squeeze/deleveraging günleri (ör. Mart 2020, Kasım 2022) simüle edilerek lineer formülün mü yoksa override kurallarının mı doğru rejimi etiketlediği test edilmelidir.

#### B. Katsayıların ($w, q, f, u$) Öznelliği ve Parametre Şişkinliği

* **Problem:** Konfigürasyondaki $w$ (ağırlık) değerlerinin elle atanması, geliştiricinin "inancını" koda yansıtır.
* **Etkilenen Bileşen:** `btc-radar` Config.
* **İlke Uyumu:** *Test Edilebilirlik* ilkesiyle çelişme riski taşır.
* **Öneri & Test:** Ağırlıklar sabit sezgisel sayılar olmak yerine, tarihsel veride rejim etiketleme başarısını optimize eden (örneğin unsupervised Unsupervised Clustering / Random Forest Importance ile elde edilen) ve periyodik güncellenen parametreler olmalıdır.

---

### 5. Ürün Konumlanışı: "Sinyal + Gerekçe, Emir Yok" Formatında Eksik Özellikler

Sanal pozisyon takibi ve karar desteği için tasarlanan bu yapıda, kullanıcıya sunulan değer ivmesini artıracak **3 kritik eksik özellik** bulunmaktadır:

1. **Dinamik Lot/Sizing Hesaplayıcı (Telegram Mesajında):**
* *Eksiklik:* Rejim Kırılganlığı $\ge 60$ olduğunda "boyut kısın" demek muğlaktır.
* *Çözüm:* Telegram bildirimine kullanıcının sabitleyeceği risk yüzdesine göre (ör. %1 Risk) direkt lot miktarı yazılmalıdır:
`Önerilen Pozisyon Büyüklüğü: 0.15 BTC (Kırılganlık nedeniyle %50 küçültüldü)`.

2. **Geçersizlik / İptal Bildirimi ("Cancel Signal"):**
* *Eksiklik:* 15m mumda sinyal geldi, ancak 3. dakikada ani bir volatilite ile rejim Güven skoru <55'e düştü veya invalidasyon seviyesine girmeden yapı bozuldu.
* *Çözüm:* Bir sonraki mumu beklemeden Telegram'a **"SİNYAL İPTAL / GEÇERSİZ (Rejim Bozuldu)"** uyarısı atan aktif izleyici.

3. **Kullanıcı İşlem Kayması Ölçer (Execution Slippage Tracker):**
* *Eksiklik:* Sinyal fiyatı $T_0$'da $65,000 iken, kullanıcının Telegram'ı görüp girdiği fiyat $65,150 olabilir.
* *Çözüm:* Telegram mesajına eklenen basit iki buton (ör. `[Girdim: $65,120]` veya `[Pas Geçtim]`) ile Kullanıcı Defteri ile Sistem Defteri arasındaki insani kaymanın Otomatik Karar Günlüğüne işlenmesi.

---

### 6. Risk: Bölüm 7'deki İtiraf Listesine Eklenmesi Gereken Maddeler

Bölüm 7'deki sınırlar listesi gayet dürüstçe hazırlanmış. Ancak şu **3 ek risk** de sistem sınırlarına eklenmelidir:

* **İtiraf 7.6 — Veri Sağlayıcı Bağımlılığı ve API Format/Rate Limit Riski:** Sistem, ticari olmayan / ücretsiz ikame API'lere (Alternative.me, CoinGecko ücretsiz planı, bitcoin-data vb.) dayanmaktadır. Bu kaynakların format değiştirmesi, yanıt vermemesi veya rate limit uygulaması durumunda `btc-radar`'ın güven skoru düşecek ve sistem sinyal üretemez (Fail-Closed kilitlenmesi) hale gelecektir.
* **İtiraf 7.7 — Vadeli/Spot Makas Bozulması (Basis Dislocation Risk):** Aşırı piyasa streslerinde Spot fiyatlar ile Binance USDT-M Vadeli fiyatları arasındaki makas (Basis) açılır. Strateji spot verisinden teyit alırken, işlem vadeli tahtada hipotetik olarak açıldığı için mum içi stoplar beklenmedik şekilde patlayabilir.
* **İtiraf 7.8 — Psikolojik Seçicilik (Cherry-Picking Bias):** Kullanıcı, Telegram'a düşen sinyallerden bazılarını kendi içsel duygusuyla (FOMO/Korku) filtreleyip bazılarına girecektir. Bu durum, sistemin sunduğu istatistiksel avantajı (expectancy) kullanıcı tarafında tamamen bozabilir.

---

### 7. Kırmızı Çizgi Kontrolü (Temel İlkelerle Çelişki Tespiti)

Dokümanda beyan edilen 3 ana ilke (*Determinizm, Test Edilebilirlik, Açıklanabilirlik*) açısından yapılan tarama sonucu:

1. **Determinizm Kontrolü: PASSED (Şartlı)**
* Canlı döngüde LLM olmaması ve strateji mantığının saf Python fonksiyonları olması determinizmi garanti eder.
* *Şart:* `btc-radar` tarafındaki API çağrılarının zaman damgaları (timestamp) ve cache mekanizması $T_0$ mumuyla tam senkronize edilmelidir (Bkz: Madde 1.A).

2. **Açıklanabilirlik Kontrolü: PASSED**
* Her sinyalin gerekçe satırı, rejim etiketi ve invalidasyon seviyesi içermesi son derece şeffaftır.

3. **Test Edilebilirlik Kontrolü: UYARI (Potansiyel Çelişki)**
* **Çelişki Noktası:** Canlı ortamda `radar-signal`'in 5 saniyelik ticker döngüsüyle stop kontrolü yapması ile Backtest'in `1m` mum verisiyle simüle edilmesi arasında **zaman çözünürlük uyumsuzluğu** vardır. 5 saniyelik döngüdeki mikro sıçramalar backtest'te test edilemez.
* **Düzeltme Önerisi:** Ya dry-run çıkış denetleyicisi de 1m mum kapanışlarına/en yüksek-en düşük değerlerine çekilmeli, ya da backtest tarafında 5s simülasyonu için slippage/spread cezası artırılmalıdır.

---

### Özet Değerlendirme ve Sonraki Adım Tavsiyesi

RADAR SİSTEMİ, bireysel bir geliştirici/QA mühendisi projesi olmanın çok ötesinde, **disiplinli bir nicel finans (quant) ürünü mimarisine** sahiptir.

Projenin **Faz D Entegrasyonuna** geçmeden önceki en kritik iki ödevi:

1. `btc-radar` veri sağlayıcıları için **Point-in-Time Önbellek/Snapshot** katmanını netleştirmek.
2. Backtest Maliyet/Slippage matrisine Rejim Kırılganlığına göre dinamik çarpan eklemektir.

Tebrik ederim, mimari kurgu son derece etkileyici.
