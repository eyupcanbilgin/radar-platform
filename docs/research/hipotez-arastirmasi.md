<!-- Kaynak: ChatGPT deep research · Alınma: 3 Ağustos 2026 · CR-001/CR-4 ve docs/hypotheses/ kartlarının kanıt kaynağı. Not: Metindeki "citeturn..." benzeri ifadeler kaynak aracın atıf işaretleridir; orijinal sohbette tıklanabilir kaynaklara karşılık gelir, sadakat için korunmuştur. -->

# BTC ve ETH İçin Intraday Fiyat Davranışları ve Test Edilebilir Edge Hipotezleri

## Araştırma çerçevesi ve sonuçların özeti

Bu çalışma, BTC ve ETH'de **15 dakika ile 1 saat arasındaki zaman dilimlerinde** test edilebilecek kısa vadeli fiyat davranışlarını araştırmaktadır. İncelenen kaynaklar; hakemli akademik makaleler, çalışma kâğıtları, resmî borsa ve veri sağlayıcı dokümantasyonu ile kurumsal piyasa araştırmalarından oluşmaktadır. Önceki metodoloji çalışmasındaki CoinGlass, CryptoQuant, CryptoMeter, AGGR.trade ve diğer veri kaynakları burada sinyalin kanıtı olarak değil, hipotezlerin uygulanmasında kullanılabilecek veri araçları olarak değerlendirilmiştir. Yer işaretleri koleksiyonundaki kaynaklar da uygulama kapsamının belirlenmesinde kullanılmıştır. fileciteturn0file0

"Edge" kelimesi burada doğrudan kârlı strateji anlamına gelmez. Çoğu akademik çalışma belirli bir geçmiş dönem, borsa, veri temizleme yöntemi ve maliyet varsayımı altında sonuç üretmektedir. Bitcoin'in yüksek frekanslı fiyatlama etkinliğinin zaman içinde geliştiğini gösteren çalışmalar da vardır; dolayısıyla geçmişte belgelenmiş bir anomalinin 2026'da aynı büyüklükte sürmesi beklenmemelidir. Özellikle daha likit BTC/USD piyasalarının zamanla daha etkin hâle geldiği, likidite yükseldikçe verimsizliğin azaldığı ve volatilite yükseldikçe fiyatlama etkinliğinin bozulabildiği belgelenmiştir. citeturn9search10

Bu raporda kanıt sınıfları şöyle kullanılmıştır:

| Kanıt düzeyi | Anlamı |
|---|---|
| **Görece yüksek** | Hakemli çalışma, birden fazla borsa veya sağlamlık testi, mümkünse dönem dışı ya da maliyet sonrası analiz |
| **Orta** | Hakemli fakat tek ana çalışma; ya da güçlü mekanizma fakat sınırlı güncel replikasyon |
| **Düşük** | Tek olay, çalışma kâğıdı, pratisyen gözlemi veya belgelenmiş veri ilişkisine dayanan fakat doğrudan test edilmemiş işlem kuralı |

Araştırmanın ana sonucu şudur: **en güçlü ve kalıcı intraday bulgular genellikle yön tahmininden çok volatilitenin ne zaman artacağı, likiditenin ne zaman değişeceği ve hangi rejimde momentum ya da ortalamaya dönüş aranması gerektiğiyle ilgilidir.** Funding, open interest, seans açılışı veya likidasyon verileri tek başına güvenilir yön sinyalleri değildir. Daha savunulabilir yaklaşım, bunları birer **rejim ve pozisyonlanma filtresi** olarak kullanıp fiyat davranışıyla teyit etmektir.

Özet değerlendirme:

| Kart | Davranış | BTC | ETH | Kanıt | Maliyet hassasiyeti |
|---|---|---:|---:|---|---|
| A | Likit ve yüksek katılımlı dönemde intraday momentum | Güçlü aday | Orta aday | Orta-yüksek | Orta |
| B | Aşırı fiyat sıçraması sonrası ortalamaya dönüş | Güçlü aday | Güçlü aday | Orta | Yüksek |
| C | Gün içi ilk aktif dönemden son aktif döneme momentum | Belgelenmiş | Replikasyon gerekli | Orta-yüksek | Düşük-orta |
| D | On beş dakikalık mum sınırı anomalisi | Belgelenmiş | Belirsiz | Orta | Çok yüksek |
| E | Aşırı funding sonrası volatilite genişlemesi | Güçlü filtre | Güçlü filtre | Orta | Orta |
| F | Perpetual–spot sapmasının normalleşmesi | Güçlü mekanizma | Güçlü mekanizma | Orta-yüksek | Yüksek |
| G | Fiyat–hacim–OI rejim ayrımı | Yararlı hipotez | Yararlı hipotez | Düşük-orta | Orta |
| H | Likidasyon kaskadında devam ve sonrasında tepki | Güçlü aday | Güçlü aday | Düşük-orta | Çok yüksek |
| I | Avrupa ve ABD açılışlarında aktivite genişlemesi | Belgelenmiş | Muhtemel | Orta-yüksek | Orta |
| J | Hafta sonunda geleneksel seans etkisinin zayıflaması | Belgelenmiş | Belgelenmiş | Orta-yüksek | Yüksek |
| K | FOMC sonrası ilk saatte volatilite sıçraması | Belgelenmiş | Belgelenmiş | Yüksek | Çok yüksek |
| L | Volatilite kümelenmesi ve rejim devamı | Belgelenmiş | Belgelenmiş | Orta-yüksek | Düşük-orta |
| M | Deribit uzlaşma ve vade saatlerinde aktivite | Belgelenmiş | Desteklenmiş | Orta-yüksek | Yüksek |
| N | Günün günü yön anomalileri | Kararsız | Kararsız | Düşük | Yüksek |

## Momentum ve ortalamaya dönüş kartları

**Kart A — Katılım ve likiditeyle koşullandırılmış kısa vadeli momentum**

**Kanıt düzeyi: Orta-yüksek**

**Davranışın tanımı.** BTC ve diğer büyük kripto paralarda intraday getirilerin bazı koşullarda aynı yönde devam ettiği, bazı koşullarda ise tersine döndüğü belgelenmiştir. Wen, Bouri, Xu ve Zhao'nun çalışması, BTC'de Mart 2013–Mayıs 2020 arasındaki yüksek frekanslı verilerde hem momentum hem reversal bulunduğunu; davranışın büyük fiyat sıçramaları, likidite, FOMC açıklamaları ve COVID dönemi gibi koşullara göre değiştiğini göstermektedir. Aynı çalışma ETH, LTC ve XRP'de de intraday tahmin edilebilirlik tespit etmiştir. Yazarlar momentumu gecikmeli bilgi işleyen yatırımcılarla, reversal davranışını ise aşırı tepki ve temel olmayan bilgiyle ilişkilendirmektedir. citeturn9search6

**Kaynak ve belgelenen dönem.** Wen, Bouri, Xu ve Zhao, *Intraday Return Predictability in the Cryptocurrency Markets: Momentum, Reversal, or Both*, 2022. Ana BTC örneklemi 3 Mart 2013–31 Mayıs 2020'dir; ETH ve diğer büyük coinlerde ek testler yapılmıştır. Çalışmanın ekonomik değer analizinde zamanlama stratejileri sürekli long ve buy-and-hold karşılaştırmalarından daha iyi sonuç üretmiştir, fakat sonuçlar 2021 sonrası piyasa yapısını kapsamaz. citeturn9search6

**Hâlâ geçerli olduğuna dair kanıt.** Momentum ailesinin 2021 sonrası tamamen kaybolduğunu gösteren bir sonuç yoktur; ancak BTC piyasasının zamanla daha etkin hâle geldiğine dair kanıt vardır. Bu nedenle etkiyi sabit bir eşikle değil, son altı veya on iki aylık rolling dağılıma göre ölçmek gerekir. citeturn9search10

**15m/1h test kuralı taslağı.**

- Son dört adet 15 dakikalık mumun toplam getirisi aynı varlığın son 60 günlük aynı saat dilimi dağılımında yüzde 80'in üzerinde olsun.
- Son bir saatlik hacim, aynı saat diliminin rolling medyanının en az 1,25 katı olsun.
- Son mum kapanışı önceki bir saatlik aralığın dışında olsun.
- Perpetual–spot farkı ve funding, son 90 günlük dağılımın aşırı yüzde 5'lik bölümünde olmasın.
- Sinyal yönünde giriş; en fazla dört adet 15 dakikalık mum taşıma.
- Çıkış: iki mumluk düşük/yüksek kırılması, 1 ATR zarar durdurma veya dört mumluk zaman çıkışı.

Bu kural, makaledeki stratejinin bire bir kopyası değil; makalenin "momentum koşullara bağlıdır" sonucunu 15 dakikalık test mimarisine çeviren bir hipotezdir.

**Zayıflıklar ve çalışmadığı rejimler.** Düşük hacimli saatlerde, fiyatın yalnızca tek borsada kırıldığı durumlarda, büyük haber öncesinde ve aşırı funding/OI birikimi sırasında sahte kırılma riski yüksektir. Momentum özellikle dar yatay aralıkta ardışık küçük zararlar üretebilir. Çok yüksek volatilitede ise yön doğru olsa bile stop mesafesi ve kayma maliyeti sonucu bozabilir.

**İşlem maliyeti hassasiyeti.** Orta düzeydedir. Dört mumluk taşıma süresi, mum-sınırı skalp stratejilerine göre daha az işlem üretir; ancak taker giriş ve taker çıkış kullanılırsa toplam maliyet küçük beklenen getiriyi tüketebilir. Maker ve taker senaryoları ayrı test edilmelidir.

**Kart B — Büyük intraday sıçrama sonrasında koşullu ortalamaya dönüş**

**Kanıt düzeyi: Orta**

**Davranışın tanımı.** Büyük ve ani fiyat hareketleri her zaman trend başlangıcı değildir. Wen ve çalışma arkadaşları, momentum ile reversal arasındaki ilişkinin büyük intraday fiyat sıçramalarının varlığında değiştiğini göstermektedir. Kripto piyasasındaki reversal davranışını aşırı tepki, yatırımcı özgüveni ve temel olmayan bilgi akışıyla ilişkilendirmektedirler. Bu sonuç, yalnızca "büyük düşüş oldu, al" gibi kör bir yaklaşımı desteklemez; asıl hipotez, aşırı hareketin devam edemediği ve emir akışının tükendiği durumda ters yönlü tepki aranmasıdır. citeturn9search6

**Kaynak ve belgelenen dönem.** Wen, Bouri, Xu ve Zhao, 2022; BTC için 2013–2020, ayrıca ETH, LTC ve XRP. Etkinin büyük jump dönemlerinde farklılaştığı ve likiditeyle koşullandığı belgelenmiştir. citeturn9search6

**Hâlâ geçerli olduğuna dair kanıt.** 2025 tasfiye olayları üzerine yapılan dakika düzeyindeki çalışmalar, çok büyük hareketlerde vadeli işlemlerin spotu önden sürükleyebildiğini, spreadlerin aşırı genişlediğini ve mark fiyatın spotun altına veya üstüne taşabildiğini göstermektedir. Bunlar reversal'ın varlığını sistematik olarak kanıtlamaz, fakat aşırı hareketlerde fiyatın geçici olarak piyasa dengesinden uzaklaşabileceği mekanizmasını destekler. citeturn12search2turn12search6

**15m/1h test kuralı taslağı.**

1. Bir 15 dakikalık getiri, aynı saat diliminin son 90 günlük mutlak getiri dağılımında yüzde 99'u aşsın veya `|return z-score| > 3` olsun.
2. Hacim z-skoru 3'ün üzerinde olsun.
3. İlk aşamada ters pozisyon açılmasın.
4. Takip eden bir veya iki mum yeni ekstrem üretemesin; fiyat şok mumunun orta noktasını geri alsın.
5. Likidasyon hacmi ilk zirvesinden en az yüzde 30 düşsün ve OI artmak yerine azalsın.
6. Şokun ters yönünde giriş; hedef şok mumunun yüzde 38–50 geri alımı, stop şok ekstremi dışı.

**Zayıflıklar ve çalışmadığı rejimler.** Temel bir bilginin yeniden fiyatlandığı FOMC, regülasyon, ETF, hack veya zincir sorunu gibi olaylarda fiyat "ortalamaya" geri dönmek zorunda değildir. Kaskad sürerken erken giriş yapmak, ortalamaya dönüş stratejisinin en önemli kuyruk riskidir. ETH'de BTC'ye göre daha yüksek beta ve daha ince likidite görülebileceğinden aynı z-skor eşikleri iki varlığa ortak uygulanmamalıdır.

**İşlem maliyeti hassasiyeti.** Yüksektir. Spread, slippage ve taker ücretleri tam da sinyalin oluştuğu anda büyür. Backtestte mum kapanış fiyatından sorunsuz işlem yapılmış varsayımı ciddi şekilde iyimser sonuç üretir.

**Kart C — İlk aktif dönemden son aktif döneme intraday momentum**

**Kanıt düzeyi: Orta-yüksek**

**Davranışın tanımı.** Bitcoin 24 saat işlem gördüğü için geleneksel anlamda sabit bir açılış ve kapanış bulunmaz. Shen, Urquhart ve Wang bu sorunu hacmi "aktif piyasa zamanı" göstergesi olarak kullanarak ele almış ve ilk yarım saat getirisinin son yarım saat getirisini pozitif yönde tahmin ettiğini bulmuştur. Tahmin gücü, ilk işlem döneminin hacim veya volatilitesinin en yüksek olduğu günlerde daha güçlüdür. Çalışmada bu momentumun özellikle BTC düşüş dönemlerinde ekonomik değer ürettiği ve geç bilgi işleyenlerden çok likidite sağlama dinamikleriyle ilişkili olduğu sonucuna varılmıştır. citeturn9search0turn9search1

**Kaynak ve belgelenen dönem.** Dehua Shen, Andrew Urquhart ve Pengfei Wang, *Bitcoin Intraday Time-Series Momentum*, Financial Review, 2022. Makale ilk kez Ekim 2021'de çevrimiçi yayımlanmış, 2022'de basılmıştır. citeturn9search0

**Hâlâ geçerli olduğuna dair kanıt.** Çalışmanın doğrudan 2024–2026 replikasyonu bulunmamaktadır. Bununla birlikte, 2026'ya kadar uzanan türev piyasası araştırmaları hacmin gün içinde belirli kurumsal saatlerde yoğunlaşmaya devam ettiğini göstermektedir. Dolayısıyla hacimle tanımlanan "sentetik açılış/kapanış" fikri yapısal olarak hâlâ makuldür; yönsel tahmin gücü yeniden ölçülmelidir. citeturn9search9turn10search1

**15m/1h test kuralı taslağı.**

- Her varlık ve borsa için son 60 günde, günün 30 dakikalık dilimlerinin ortalama hacmini hesapla.
- Günlük en aktif sekiz saatlik bloğu veya Avrupa–ABD çakışma bloğunu "işlem seansı" olarak tanımla.
- Seansın ilk 30 dakikasındaki getirinin işaretini kaydet.
- İlk yarım saatin hacmi kendi rolling dağılımının yüzde 70'inden yüksekse, seansın son 30 veya 60 dakikasında aynı yönde pozisyon aç.
- Pozisyonu seans bitiminde kapat; sonraki güne taşıma.
- BTC ve ETH'yi ayrı kalibre et; ETH işlemine BTC ilk dönem getirisini ek açıklayıcı değişken olarak ayrıca test et.

**Zayıflıklar ve çalışmadığı rejimler.** Sonuç, seans tanımına çok duyarlıdır. UTC gün sınırı, borsa sunucu saati veya Türkiye saatiyle keyfî gün oluşturmak sahte sonuç üretebilir. Ayrıca 24/7 piyasa yapısında "ilk" ve "son" kavramları araştırmacı seçimine bağlıdır.

**İşlem maliyeti hassasiyeti.** Düşük-ortadır. Günde en fazla bir veya birkaç işlem üretmesi avantajdır. Bununla birlikte seansın son bölümünde spread ve volatilite yapısı borsaya göre değişebilir.

**Kart D — On beş dakikalık mum sınırı etkisi**

**Kanıt düzeyi: Orta**

**Davranışın tanımı.** Bir çalışma, BTC'nin pozitif dakikalık getirilerinin orantısız biçimde 15 dakikalık mumların başladığı 00, 15, 30 ve 45'inci dakikaların çevresinde toplandığını bulmuştur. Çalışmadaki ortalama etki sınır dakikalarında dakikada yaklaşık 0,58 baz puandır; diğer dakikalardaki ortalama getiriler negatiftir. Etki yedi borsada gözlenmiş, orta–geç 2020 döneminde ortaya çıkmış, farklı istatistiksel kontroller ve dönem dışı testlerde sürmüştür. Yazarlar olası açıklama olarak 15 dakikalık mum kapanışlarına tepki veren algoritmik işlemleri göstermektedir. citeturn9search2

**Kaynak ve belgelenen dönem.** *Turn-of-the-Candle Effect in Bitcoin Returns*, Heliyon, 2023. Çalışma yedi Bitcoin borsasını kapsamış; anomali örneklem boyunca değil, esas olarak 2020'nin orta ve son dönemlerinden itibaren ortaya çıkmıştır. citeturn9search2

**Hâlâ geçerli olduğuna dair kanıt.** Makalede dönem dışı test bulunmasına rağmen 2024–2026'ya uzanan bağımsız bir replikasyon tespit edilmemiştir. Anomalinin algoritmik işlemciler tarafından keşfedildikten sonra küçülmesi olasıdır. Bu nedenle güncel dönemde ayrı bir holdout örneklemi zorunludur.

**15m/1h test kuralı taslağı.**

- Bu hipotez yalnızca 15 dakikalık OHLC ile sağlıklı test edilemez; en az bir dakikalık veya tick veri gerekir.
- Her 15 dakikalık sınırdan 30–60 saniye önce long giriş ve sınırdan 60–120 saniye sonra çıkış test edilebilir.
- Alternatif olarak, sınır dakikasındaki market-order imbalance pozitifse yalnızca long alınabilir.
- BTC ve ETH ayrı test edilmeli; ilk çalışma yalnızca BTC için doğrudan kanıt sunmaktadır.
- Sonuç, "always long" dışında önceki mum yönü, hacim ve volatilite rejimine göre alt gruplara ayrılmalıdır.

**Zayıflıklar ve çalışmadığı rejimler.** Bu tür bir etki keşfedilmeye ve arbitraj edilmeye çok açıktır. Borsa API zaman damgası hataları, mum oluşturma standardı, saat senkronizasyonu ve survivorship bias sonucu bozabilir.

**İşlem maliyeti hassasiyeti.** Çok yüksektir. Makale maliyet sonrası sonuç bildirse de güncel taker ücretleri, spread ve kuyruk pozisyonu tekrar ölçülmelidir. Birkaç baz puanlık ek kayma anomalinin tamamını silebilir.

## Türevler, bazis, open interest ve likidasyon kartları

**Kart E — Aşırı funding yön sinyalinden çok yaklaşan volatilite filtresidir**

**Kanıt düzeyi: Orta**

**Davranışın tanımı.** Perpetual funding, perpetual kontratın spot fiyattan kalıcı olarak kopmasını engelleyen ödeme mekanizmasıdır. Pozitif funding'de longlar shortlara, negatif funding'de shortlar longlara ödeme yapar. Ancak yüksek pozitif funding otomatik olarak fiyatın düşeceği anlamına gelmez. Coinbase Institutional'ın analizi, fiyat hareketinin sıklıkla funding artışından önce geldiğini ve yüksek funding'in fiyat için bağımsız öncü gösterge olmaktan çok yükselen pozisyonlanmanın gecikmeli sonucu olabileceğini belirtmektedir. Aynı analiz, kalıcı yüksek funding dönemlerinin yüksek volatilite dönemlerinden önce gelebileceğini göstermektedir. citeturn11search0

Funding oranları borsadan borsaya aynı ölçekle yayımlanmaz. Örneğin sekiz saatlik yüzde 0,01 ile saatlik yüzde 0,01 aynı yıllık maliyete karşılık gelmez; karşılaştırma öncesi annualize edilmesi veya ortak zaman ölçeğine çevrilmesi gerekir. Coinbase ayrıca funding formüllerindeki taban faiz ve clamp yapılarının dağılımı pozitif tarafa eğebildiğini belirtmektedir. citeturn11search0turn11search9

**Kaynak ve belgelenen dönem.** David Han ve David Duong, Coinbase Institutional, *A Primer on Perpetual Futures*, 2024. Analizde 2022–2024'e uzanan CEX verileri ve OI ağırlıklı BTC funding oranları kullanılmıştır. Teorik temel, perpetual fiyatının funding yoluyla spota bağlandığını gösteren Ackerer, Hugonnier ve Jermann'ın 2023 çalışmasıyla desteklenmektedir. citeturn11search0turn11academia25

**Hâlâ geçerli olduğuna dair kanıt.** Funding mekanizması perpetual ürün tasarımının temel parçası olduğu için yapısal olarak geçerlidir. Fakat funding aşırılığının fiyat yönünü tahmin ettiği iddiası için güçlü ve kalıcı kanıt yoktur. 2024–2026 kurumsal piyasa yorumlarında yüksek funding ve geniş OI, yükselişin kırılganlığı veya yaklaşan volatilite açısından kullanılmaya devam edilmektedir. citeturn11search3turn11search6turn11search7

**15m/1h test kuralı taslağı.**

- Tüm borsaların funding oranlarını saatlik eşdeğere dönüştür.
- OI ağırlıklı birleşik BTC ve ETH funding serisi oluştur.
- Funding z-skoru 2'nin, OI z-skoru 1'in üzerindeyse "yüksek kaldıraçlı volatilite rejimi" tanımla.
- Bu rejimde dar aralık mean-reversion stratejilerini kapat.
- Fiyat bir saatlik aralığı hacimle kırarsa momentum girişine izin ver.
- Contrarian işlem yalnızca fiyat yeni ekstrem üretemezken funding ve OI yüksek kalıyorsa test edilsin.
- Çıkış funding normale döndüğünde, OI yüzde 5–10 azaldığında veya dört saat sonunda.

**Zayıflıklar ve çalışmadığı rejimler.** Funding yükseliş trendi boyunca haftalarca pozitif kalabilir. Mutlak funding eşikleri borsa formülleri değiştikçe bozulur. Funding'in yayınlanma zamanı ile ödeme zamanı karıştırılmamalıdır.

**İşlem maliyeti hassasiyeti.** Orta düzeydedir. Yönlü perp işlemlerinde ücret ve spread yanında pozisyon funding zamanını geçiyorsa funding ödemesi de P&L'ye eklenmelidir.

**Kart F — Perpetual–spot sapmasının normalleşmesi**

**Kanıt düzeyi: Orta-yüksek**

**Davranışın tanımı.** Perpetual kontratın spot fiyatından ayrılması, arbitrajcılar ve funding mekanizması sayesinde genellikle kalıcı değildir. Ackerer, Hugonnier ve Jermann perpetual fiyatını teorik olarak spot ve funding mekanizmasına bağlayan arbitrajsız fiyatlama çerçevesi geliştirmiştir. He, Manela, Ross ve von Wachter ise işlem maliyetlerini içeren teorik sınırlar üretmiş; kripto perpetual fiyatlarında teorik değerden sapmaların geleneksel döviz piyasalarına göre büyük olduğunu, farklı coinlerde birlikte hareket ettiğini ve zaman içinde küçüldüğünü göstermiştir. citeturn11academia25turn11academia26

Buradaki edge genellikle yönlü değil, **delta-neutral yakınsama** edge'idir: perp pahalıysa spot long–perp short; perp ucuzsa ters yapı. Ancak ikinci yapı spot shortlama, borç alma ve teminat operasyonları nedeniyle daha zordur.

**Kaynak ve belgelenen dönem.** Ackerer, Hugonnier ve Jermann, *Perpetual Futures Pricing*, 2023; He, Manela, Ross ve von Wachter, *Fundamentals of Perpetual Futures*, 2022. İlk çalışma teorik, ikincisi teoriye ek olarak kripto piyasasındaki sapmaların ampirik davranışını incelemektedir. citeturn11academia25turn11academia26

**Hâlâ geçerli olduğuna dair kanıt.** Funding ve premium mekanizması hâlen güncel perpetual ürünlerinin merkezindedir. Coinbase'in resmî ürün dokümantasyonu, funding'in futures mark ile spot mark arasındaki farkın saat içindeki ölçümlerinden üretildiğini göstermektedir. Dolayısıyla yakınsama mekanizması sürmektedir; edge büyüklüğü ise artan arbitraj rekabetiyle küçülmüş olabilir. citeturn11search9

**15m/1h test kuralı taslağı.**

- Aynı veya ekonomik olarak eşleşen spot ve perp endeksini kullan:
  `premium = (perp_mid - spot_mid) / spot_mid`.
- Premium'u son 30 veya 90 günlük aynı saat dağılımına göre standardize et.
- `premium z > 3`, beklenen funding pozitif ve tüm tahmini işlem maliyetlerinin üzerindeyse spot long–perp short.
- Premium z-skoru 0,5'in altına döndüğünde veya maksimum altı saat sonunda kapat.
- Her iki bacağın aynı anda gerçekleştiği varsayılmamalı; legging risk simülasyonu yapılmalı.
- ETH ve BTC için borrow, teminat ve borsa riski ayrı modellenmeli.

**Zayıflıklar ve çalışmadığı rejimler.** Büyük fiyat hareketlerinde premium daha da açılabilir. Borsalar arası arbitrajda para transferi gecikmesi, karşı taraf riski ve farklı endeks fiyatları vardır. Ters arbitrajda spot borçlanma maliyeti edge'i yok edebilir. Stablecoin depeg riski yanlış premium sinyali oluşturabilir.

**İşlem maliyeti hassasiyeti.** Çok yüksektir. İki bacakta komisyon, spread ve slippage ödenir; ayrıca funding, borrow, transfer ve sermaye maliyeti vardır. Mid-price backtest kullanılmamalıdır.

**Kart G — Fiyat, hacim ve open interest'in birlikte okunması**

**Kanıt düzeyi: Düşük-orta**

**Davranışın tanımı.** Hacim, belirli sürede gerçekleşen işlem miktarını; OI ise kapanmamış türev kontratlarını gösterir. Bu iki değişken aynı şeyi ölçmez. BTC spot ve futures piyasalarını yüksek frekanslı verilerle inceleyen Conlon, Corbet ve McGee, beklenmedik spot hacminin gerçekleşen volatilitenin önemli açıklayıcılarından biri olduğunu, buna karşılık CME futures hacminin sistemik volatiliteye katkısının sınırlı veya yatıştırıcı olduğunu bulmuştur. Bu sonuç, hacmin hangi piyasadan geldiğinin önemli olduğunu gösterir. citeturn10search8

Pratisyenler arasında kullanılan "fiyat yükseliyor ve OI yükseliyorsa yeni longlar geliyor" yorumu eksiktir; OI yön içermez ve her long kontratın karşısında bir short vardır. Yine de fiyat, hacim, funding ve OI birlikte kullanıldığında hareketin yeni pozisyon açılışından mı yoksa pozisyon kapanışından mı geldiğine dair test edilebilir rejimler oluşturulabilir. Coin Metrics, OI, funding, liquidation, trade, quote ve order-book verilerini ayrı veri kümeleri olarak sunmaktadır. citeturn10search6turn11search8

**Kaynak ve belgelenen dönem.** Conlon, Corbet ve McGee, *The Bitcoin Volume–Volatility Relationship: A High Frequency Analysis of Futures and Spot Exchanges*, 2024. Çalışma, beş büyük spot borsa ve CME referans fiyatına dayanan yüksek frekanslı gerçekleşen volatilite ölçüleri kullanmıştır. citeturn10search8

**Hâlâ geçerli olduğuna dair kanıt.** Hacim–volatilite ilişkisi yapısal olarak güçlüdür; fakat aşağıdaki dört-kadran işlem yorumu doğrudan akademik olarak doğrulanmış sabit bir edge değildir. Bu nedenle fiyat–OI kuralı bağımsız hipotez olarak test edilmelidir.

**15m/1h test kuralı taslağı.**

| Fiyat | OI | Hacim | Test edilecek yorum |
|---|---|---|---|
| Yükseliyor | Yükseliyor | Yüksek | Yeni pozisyonlarla momentum; funding aşırı değilse devam |
| Yükseliyor | Düşüyor | Yüksek | Short kapanışı; hareketin takip gücü daha kısa olabilir |
| Düşüyor | Yükseliyor | Yüksek | Yeni short veya hedging; negatif momentum |
| Düşüyor | Sert düşüyor | Çok yüksek | Long tasfiyesi/pozisyon kapanışı; ilk aşamada devam, sonra tepki adayı |

Somut kural:

- 1 saatlik fiyat kırılması + hacim z-skoru > 1,5 + ΔOI z-skoru > 1: kırılma yönünde giriş.
- Aynı fiyat kırılması sırasında ΔOI < −2 ise pozisyonu daha kısa taşı veya giriş yapma.
- ΔOI sert negatif, likidasyon yüksek ve fiyat sonraki iki mumda yeni ekstrem yapamıyorsa reversal kartına geç.

**Zayıflıklar ve çalışmadığı rejimler.** USD cinsinden OI, fiyat yükseldiğinde kontrat sayısı değişmese bile artabilir. Bu nedenle coin cinsinden ve USD cinsinden OI birlikte tutulmalıdır. Borsalar arası taşıma ve hedge pozisyonları yön yorumunu bozar.

**İşlem maliyeti hassasiyeti.** Orta düzeydedir. Kural genellikle yüksek hacimli kırılmalarda çalışacağı için spread görece iyi olabilir; ancak sert OI düşüşü dönemlerinde slippage hızla büyür.

**Kart H — Likidasyon kaskadında iki aşamalı davranış: önce devam, sonra tepki**

**Kanıt düzeyi: Düşük-orta**

**Davranışın tanımı.** Otomatik tasfiyeler fiyat hareketini kendi kendini besleyen bir sürece çevirebilir. Fiyat düşer, kaldıraçlı longlar tasfiye edilir, tasfiye satışları fiyatı daha da düşürür ve yeni tasfiyeleri tetikler. Dakika düzeyinde Ekim 2025 kaskadını inceleyen bir çalışma, futures fiyatlarının spotu önden sürüklediğini, hacmin fiyat dibinden önce normalin 22 katına çıktığını, basis'in sekiz dakika içinde büyük yön değiştirdiğini ve mark fiyatın spot ile futures fiyatının altına taşarak geri besleme oluşturduğunu bildirmiştir. Ancak bu sonuç tek büyük olaya dayandığı için kalıcı bir edge olarak kabul edilmemelidir. citeturn12search2

Aynı olay çevresinde Hyperliquid order book verisini inceleyen çalışma, spreadlerin olay gününde hızla toparlanmaya başladığını fakat order-book derinliğinin daha uzun süre zayıf kaldığını göstermiştir. Bu bulgu, fiyat ve spread normale dönse bile piyasa dayanıklılığının tam geri gelmemiş olabileceğini düşündürür. citeturn12search6turn12search7

**Kaynak ve belgelenen dönem.** Boon Chuan Lim, *Anatomy of a Crypto Cascade*, 2026; BTC, ETH ve SOL için Binance ve Bybit spot, perp ve mark fiyatlarının 10 Ekim 2025 olayındaki dakika verileri. Aynı yazarın ikinci çalışması Hyperliquid'de BTC, ETH, SOL, XRP ve DOGE için olay etrafındaki 92 günlük order-book panelini kullanmıştır. Her ikisi de çalışma kâğıdıdır ve hakemli geniş örneklem kanıtı değildir. citeturn12search2turn12search6

**Hâlâ geçerli olduğuna dair kanıt.** Tasfiye mekanizması güncel perpetual piyasalarda devam etmektedir. Coin Metrics, kısa pozisyonları kapatan liquidation buy emirleri ile long pozisyonları kapatan liquidation sell emirlerini beş dakikalık ve saatlik düzeyde ölçmektedir. Mekanizma geçerli olsa da "kaskad sonrası mutlaka tepki gelir" sonucu kanıtlanmış değildir. citeturn10search12

**15m/1h test kuralı taslağı.**

**Kaskad devam sinyali:**

- 15 dakikalık mutlak getiri z-skoru > 3.
- Aynı yönlü liquidation USD z-skoru > 4.
- Hacim z-skoru > 4.
- OI bir mum içinde yüzde 3 veya rolling dağılımın alt yüzde 1'i kadar düşsün.
- Fiyat her mumda yeni ekstrem yapıyorsa ters pozisyon açma; mevcut momentum yönünü en fazla bir veya iki mum takip et.

**Kaskad sonrası tepki sinyali:**

- Likidasyon miktarı iki ardışık mumda azalsın.
- OI düşüşü yavaşlasın.
- Perp–spot premium aşırı seviyeden normale dönmeye başlasın.
- Fiyat şok mumunun son çeyreğini geri alsın.
- Ters yönlü pozisyon; hedef şokun yüzde 25–50 geri alımı, stop yeni ekstrem.

**Zayıflıklar ve çalışmadığı rejimler.** Tek olaydan genelleme riski yüksektir. Borsaların bildirdiği liquidation verisi eksik olabilir. ADL, sigorta fonu, mark price ve liquidation motoru borsadan borsaya değişir. Sistemik haberlerde tepki oluşmadan ikinci bir satış dalgası gelebilir.

**İşlem maliyeti hassasiyeti.** Çok yüksektir. Normal backtest ücretlerinden çok, kuyruk kayması ve gerçekleşmeyen emirler önemlidir. En azından 10, 25 ve 50 baz puanlık stres slippage senaryoları kullanılmalıdır.

## Seans, takvim ve volatilite kartları

**Kart I — Avrupa ve ABD piyasa açılışlarında hacim ve volatilite genişlemesi**

**Kanıt düzeyi: Orta-yüksek**

**Davranışın tanımı.** Kripto piyasaları 24/7 açık olsa da insan ve kurumsal faaliyet 24 saate eşit dağılmaz. Eross, McGroarty, Urquhart ve Wolfe, dört yıllık BTC tick verisini beş dakikaya toplayarak gerçekleşen volatilitenin üç büyük küresel hisse piyasasının açılış saatlerinde yükseldiğini, likiditenin büyük piyasa açılışları civarında arttığını ve erken sabah saatlerinde piyasanın daha illikit olduğunu bulmuştur. citeturn9search3turn10search2

Başka bir çalışma, BTC hacmi ve volatilitesinin Avrupa ve ABD borsalarının gündüz saatleriyle çakışan dönemlerde daha yüksek olduğunu, Asya açılışının volatilite üzerinde daha sınırlı etkisi bulunduğunu ve hafta içi aktivitenin hafta sonundan belirgin biçimde yüksek olduğunu göstermiştir. citeturn10search7

**Kaynak ve belgelenen dönem.** Eross, McGroarty, Urquhart ve Wolfe, *The Intraday Dynamics of Bitcoin*, 2019; dört yıllık 5 dakikalık BTC verisi. Ek kanıt, *Time-of-Day Periodicities of Trading Volume and Volatility in Bitcoin Exchange: Does the Stock Market Matter?*, 2020 civarı yayımlanan yüksek frekanslı çalışma. citeturn9search3turn10search7

**Hâlâ geçerli olduğuna dair kanıt.** Deribit BTC opsiyonları, CME BTC futures ve Deribit ETH opsiyonlarını 2025'e kadar inceleyen 2026 tarihli çalışma, aktivitenin 08:00–09:00 ve 14:00–15:00 GMT dönemlerinde yoğunlaşmaya devam ettiğini göstermektedir. ABD açılışıyla bağlantılı ikinci tepe hafta sonlarında zayıflamaktadır. citeturn9search9turn10search1

**15m/1h test kuralı taslağı.**

- Saatleri sabit İstanbul saatiyle değil, `Europe/London` ve `America/New_York` zaman dilimleriyle tanımla; yaz saati değişimini otomatik uygula.
- Londra ve New York açılışından önceki 60 dakikanın high–low aralığını oluştur.
- Açılıştan sonraki ilk 15 dakika kapanışı bu aralığın dışında ve hacim z-skoru > 1 ise kırılma yönünde giriş.
- Maksimum taşıma süresi dört adet 15 dakikalık mum.
- İlk mum çift taraflı geniş wick ve kapanış aralık içinde ise işlem yapma.
- Asya açılışı ayrı model olsun; Avrupa/ABD parametreleri kopyalanmasın.

**Zayıflıklar ve çalışmadığı rejimler.** Belgelenen güçlü sonuç yön değil, hacim ve volatilite artışıdır. Açılış kırılması devam da edebilir, tersine de dönebilir. ABD tatilleri, erken kapanışlar ve yaz saati geçiş haftaları ayrıca etiketlenmelidir.

**İşlem maliyeti hassasiyeti.** Orta düzeydedir. Hacim artışı spreadi daraltabilir, fakat haberli açılışlarda hız ve slippage büyür.

**Kart J — Hafta sonunda geleneksel piyasa etkisinin ve likiditenin zayıflaması**

**Kanıt düzeyi: Orta-yüksek bir rejim filtresi; düşük bir yön sinyali**

**Davranışın tanımı.** Hafta sonlarında BTC ve ETH işlem görmeye devam eder, ancak geleneksel piyasa katılımcıları, ETF'ler ve birçok kurumsal masa aktif değildir. Geniş bir çalışmada yedi BTC borsasından 15 milyondan fazla gözlem kullanılarak hafta sonu işlem hacminin daha düşük olduğu, fakat günün saati veya haftanın günü bazındaki yönsel getiri anomalilerinin zaman içinde kalıcı olmadığı bulunmuştur. citeturn10search10

2026 tarihli opsiyon çalışması da New York açılışıyla bağlantılı aktivite tepesinin hafta sonlarında büyük ölçüde kaybolduğunu, buna karşılık Deribit'in 08:00 GMT settlement etkisinin hafta sonunda sürdüğünü göstermektedir. Bu, bütün zaman etkilerinin hafta sonunda aynı şekilde kaybolmadığını gösterir. citeturn9search9turn12search1

**Kaynak ve belgelenen dönem.** *Bitcoin Time-of-Day, Day-of-Week and Month-of-Year Effects in Returns and Trading Volume*, 2019; yedi küresel BTC borsası ve 15 milyondan fazla gözlem. Ek güncel kanıt Deribit verisini 2016–Ağustos 2025 arasında inceleyen 2026 çalışmasıdır. citeturn10search10turn12search1

**Hâlâ geçerli olduğuna dair kanıt.** 2025'e kadar uzanan türev verisi, ABD seansı bağlantısının hafta sonunda zayıfladığını doğrulamaktadır. Ancak hafta sonunun kendisi için kalıcı pozitif veya negatif yönsel getiri kanıtı yoktur.

**15m/1h test kuralı taslağı.**

- Hafta içi ve hafta sonu modellerini tamamen ayır.
- Hafta sonu aynı volatiliteye karşı pozisyon büyüklüğünü yüzde 25–50 azaltan senaryoları test et.
- Breakout girişinde hafta içinden daha yüksek hacim teyidi iste.
- Tek borsa kırılması yerine en az iki spot ve iki perp borsasında eş zamanlı kırılma şartı kullan.
- Cumartesi/Pazar yön sinyali oluşturma; yalnızca eşik ve execution filtresi olarak test et.

**Zayıflıklar ve çalışmadığı rejimler.** Büyük politik, jeopolitik veya kriptoya özgü haberler hafta sonu gerçekleşebilir ve düşük likidite hareketi büyütebilir. Daha düşük hacim her zaman daha düşük volatilite demek değildir.

**İşlem maliyeti hassasiyeti.** Yüksektir. Spread ve market impact özellikle düşük likiditeli hafta sonu saatlerinde genişleyebilir.

**Kart K — FOMC açıklaması sonrası ilk saatte belirgin volatilite ve hacim sıçraması**

**Kanıt düzeyi: Görece yüksek, fakat yönsel değil**

**Davranışın tanımı.** FOMC açıklamaları BTC ve ETH için planlanabilir bir intraday volatilite olayıdır. Ocak 2021–Ocak 2026 arasındaki 41 planlı FOMC açıklamasını inceleyen çalışma, açıklamadan sonraki ilk saatte BTC'nin ortalama mutlak getirisinin yüzde 0,66'dan yüzde 1,25'e, ETH'nin yüzde 0,85'ten yüzde 1,50'ye çıktığını bulmuştur. Aynı saatte USD hacmi BTC'de 2,54, ETH'de 2,81 katına yükselmiştir. Eşleştirilmiş hafta, aynı saat placebo, HAC regresyonu ve Bitfinex replikasyonu sonuçları desteklemiştir. citeturn10search3

**Kaynak ve belgelenen dönem.** *Scheduled FOMC Statements and Intraday Macro Event Risk in Cryptocurrency Markets*, Finance Research Letters, 2026. 41 açıklama; Ocak 2021–Ocak 2026; saatlik BTC–USD ve ETH–USD mumları. citeturn10search3

**Hâlâ geçerli olduğuna dair kanıt.** Örneklem Ocak 2026'ya kadar uzandığı için rapordaki en güncel sistematik bulgulardan biridir. Ancak sonuç, volatilite ve hacim üzerinedir; açıklamanın sürpriz içeriği bilinmeden yön tahmini üretmez.

**15m/1h test kuralı taslağı.**

İki ayrı hipotez test edilmelidir:

**Riskten kaçınma modeli**

- Açıklamadan 30 dakika önce tüm mean-reversion işlemlerini kapat.
- Açıklamadan sonraki ilk 30–60 dakika yeni pozisyon açma.
- Bu model doğrudan P&L edge değil, kuyruk kaybını azaltan risk filtresidir.

**Açılış aralığı kırılma modeli**

- Açıklama öncesi 60 dakikanın high–low aralığını kaydet.
- İlk 15 dakikada işlem açma.
- İkinci 15 dakikalık mum açıklama öncesi aralık ve ilk mum ekstremi dışında kapanırsa aynı yönde giriş.
- Hacim, aynı saat dağılımının yüzde 90'ının üzerinde olsun.
- En geç açıklamadan 60–90 dakika sonra çık.

**Zayıflıklar ve çalışmadığı rejimler.** FOMC statement, noktasal tahminler ve basın toplantısı farklı zamanlarda ikinci dalgalar oluşturabilir. İlk hareket sahte olabilir. Makale yön devamını değil, mutlak hareketi kanıtlamaktadır.

**İşlem maliyeti hassasiyeti.** Çok yüksektir. Spread, slippage ve veri gecikmesi olağan saatlerden farklıdır. Backtestte açıklama tam zaman damgası, mum kapanışı ve gerçekçi gecikme kullanılmalıdır.

**Kart L — Volatilite kümelenmesi, rough volatility ve rejim devamı**

**Kanıt düzeyi: Orta-yüksek volatilite tahmini; orta-düşük yön stratejisi**

**Davranışın tanımı.** Kripto volatilitesi bağımsız ve rastgele dağılmaz; yüksek volatilite dönemleri başka yüksek volatilite dönemlerini, sakin dönemler başka sakin dönemleri takip etme eğilimindedir. BTC realized volatility üzerine yapılan 2025 çalışması, beş dakikalık realized volatility ölçümünün yüksek hassasiyete sahip olduğunu ve volatilitenin rough/multifraktal özellikler taşıdığını göstermektedir. citeturn10academia37turn12academia24

Bitcoin implied volatility'sini beş dakikalık ufukta inceleyen başka bir çalışma, gecikmeli fiyat ve volatilite hareketlerinin gelecekteki kısa vadeli volatiliteyi mütevazı ölçüde tahmin edebildiğini bulmuştur. citeturn10academia38turn12academia25

BTC ve ETH'yi Coinbase Pro, Binance ve Uniswap üzerinde inceleyen Hansen, Kim ve Kimbrough ise volatilite ve hacimde haftanın günü, günün saati ve saat içi periyodiklikler bulunduğunu, bu örüntülerin zamanla güçlendiğini ve funding saatleri ile algoritmik işlemlerle ilişkili olabileceğini göstermiştir. citeturn10academia39turn12academia27

**Kaynak ve belgelenen dönem.** Hansen, Kim ve Kimbrough, *Periodicity in Cryptocurrency Volatility and Liquidity*, 2021; BTC ve ETH, iki merkezi borsa ve Uniswap V2. Pervaiz ve diğerleri, *Fear and Volatility in Digital Assets*, 2020; beş dakikalık BTC volatilitesi. Takaishi, *Multifractality and Sample Size Influence on Bitcoin Volatility Patterns*, 2025. citeturn10academia39turn12academia25turn12academia24

**Hâlâ geçerli olduğuna dair kanıt.** 2025 tarihli rough-volatility çalışması, volatilite kalıcılığının daha yeni BTC verilerinde de araştırılmaya devam ettiğini göstermektedir. Buna rağmen "yüksek vol = momentum, düşük vol = mean reversion" eşlemesi doğrudan kanıtlanmış evrensel bir kural değildir; test edilecek stratejik yorumdur.

**15m/1h test kuralı taslağı.**

- `RV_short`: son dört adet 15 dakikalık getirinin kareleri toplamı.
- `RV_long`: son 96 adet 15 dakikalık getirinin kareleri ortalaması.
- `regime_ratio = RV_short / RV_long`.
- Oran yüzde 80'in üzerindeyse yüksek volatilite rejimi; kırılma ve momentum kartlarına izin ver.
- Oran yüzde 20'nin altındaysa düşük volatilite rejimi; yalnızca range sınırında mean reversion test et.
- Oran kısa sürede yüzde 20'den yüzde 80'e çıkarsa "rejim geçişi" olarak tanımla ve pozisyon boyutunu azalt.
- Saat içi periyodik yapıyı temizlemek için getirileri aynı saat diliminin tarihsel volatilitesine böl.

**Zayıflıklar ve çalışmadığı rejimler.** Volatilite yön vermez. Sakin rejim, büyük bir haberden hemen önce oluşabilir. Sabit ATR eşiği uzun dönemde BTC fiyat seviyesi ve piyasa olgunluğu değiştikçe bozulur.

**İşlem maliyeti hassasiyeti.** Rejim filtresinin kendisi az işlem ürettiği için düşüktür. Ancak filtre üzerine kurulan mean-reversion sistemi yüksek turnover üretirse maliyet hassasiyeti artar.

**Kart M — Deribit settlement, expiry ve kurumsal saatlerde aktivite yoğunlaşması**

**Kanıt düzeyi: Orta-yüksek aktivite; düşük-orta yön**

**Davranışın tanımı.** Deribit BTC opsiyonlarında işlem hacmi 08:00–09:00 GMT ve 14:00–15:00 GMT aralıklarında yoğunlaşmaktadır. İlk tepe, Deribit'in 08:00 GMT günlük settlement ve expiry mekanizmasıyla ilişkilidir; hafta sonunda da sürer ve vade sonu kontrat miktarının yüksek olduğu günlerde güçlenir. İkinci tepe ABD hisse piyasası açılışıyla ilişkilidir ve hafta sonunda zayıflar. Aynı çalışmada CME BTC futures ve Deribit ETH opsiyonlarından elde edilen ek sonuçlar, etkinin tek bir ürünle sınırlı olmadığını desteklemektedir. citeturn9search9turn10search0turn12search1

**Kaynak ve belgelenen dönem.** *Time-of-Day Effects in the Bitcoin Options Market*, Finance Research Letters, Temmuz 2026. Deribit verisi Kasım 2016–17 Ağustos 2025 dönemini kapsamaktadır. CME BTC futures verisi de Aralık 2017–Ağustos 2025 dönemini kapsamaktadır. citeturn10search1turn12search1

**Hâlâ geçerli olduğuna dair kanıt.** Örneklem Ağustos 2025'e kadar uzandığı için bulgu günceldir. Bununla birlikte belgelenen davranış hacim yoğunlaşmasıdır; bu saatlerde otomatik olarak pozitif veya negatif getiri oluştuğu kanıtlanmamıştır.

**15m/1h test kuralı taslağı.**

- 07:45–08:00 UTC öncesi aralığı ve 08:00 sonrası ilk 15 dakikayı ayrı tanımla.
- Günlük, haftalık ve aylık expiry günlerine ayrı etiket ekle.
- ATM option OI veya sona eren notional rolling yüzde 80'in üzerindeyse olay penceresini aktif kabul et.
- İlk 15 dakikalık yön yerine ikinci mumdaki devam veya geri dönüş ayrı modeller olarak test edilsin.
- 14:00–15:00 GMT penceresi hafta içi ve hafta sonu ayrı tahmin edilsin.
- ETH'de Deribit option OI ve BTC aynı saat getirisi ek özellik olarak kullanılabilir.

**Zayıflıklar ve çalışmadığı rejimler.** Opsiyon aktivitesinin yüksek olması spotta yönsel fiyat baskısı olduğu anlamına gelmez. Gamma yönünü tahmin etmek için yalnızca toplam OI yeterli değildir; strike, vade, call/put ve dealer pozisyon varsayımları gerekir.

**İşlem maliyeti hassasiyeti.** Yüksektir. Settlement çevresindeki kısa ömürlü hareketler hız ve execution kalitesine duyarlıdır.

## Kanıtı düşük hipotezler

Bu bölümdeki davranışlar araştırmaya değerdir, fakat doğrudan "edge" olarak kullanılmaları için kanıt yetersizdir.

**Kart N — Haftanın günü bazında momentum veya anti-momentum**

**Kanıt düzeyi: Düşük**

**Davranışın tanımı.** Bazı çalışmalar belirli günlerde farklı persistence veya multifraktal davranışlar bulsa da geniş borsa örneklemli araştırmalar BTC getirilerindeki gün, saat ve ay anomalilerinin zaman içinde kalıcı olmadığını göstermektedir. Kalıcı görülen ana davranış, hafta sonunda hacmin düşmesidir; yönsel Pazartesi, Cuma veya hafta sonu etkisi değildir. citeturn10search10

**Test kuralı taslağı.** Mevcut stratejinin işlemlerini haftanın gününe göre grupla; her gün için Sharpe veya ortalama getiriyi ayrı optimize etme. Önce sabit stratejinin gün bazında performans farkını out-of-sample test et. Çoklu hipotez düzeltmesi uygula.

**Zayıflıklar.** Yedi gün, iki varlık, çok sayıda saat ve farklı yön eşikleri birlikte tarandığında data mining riski çok büyüktür.

**Maliyet hassasiyeti.** Yüksektir; bildirilen brüt farkların çoğu küçük olabilir.

**Kart O — Aşırı funding'i kör biçimde tersine işlem yapmak**

**Kanıt düzeyi: Düşük**

**Davranışın tanımı.** "Funding çok pozitif, short aç" veya "funding negatif, long aç" popüler bir contrarian kuraldır. Ancak Coinbase'in incelemesi fiyatın çoğu zaman funding'i önden sürüklediğini, yüksek funding'in doğrudan fiyat öncüsü olmadığını belirtmektedir. Yüksek funding güçlü trend sırasında uzun süre devam edebilir. citeturn11search0

**Test kuralı taslağı.** Contrarian giriş yalnızca üçlü teyitle test edilmelidir: funding z-skoru aşırı, OI aşırı ve fiyat yeni ekstrem yapamıyor. Funding tek başına sinyal olduğunda ayrı benchmark oluşturulmalı.

**Zayıflıklar.** Trend piyasasında seri zarar ve sınırsıza yakın squeeze riski vardır.

**Maliyet hassasiyeti.** Orta-yüksek; yanlış yönde funding alınsa bile fiyat zararı funding gelirinden çok büyük olabilir.

**Kart P — Aşırı perpetual–spot basis'in BTC/ETH yönünü tahmin etmesi**

**Kanıt düzeyi: Düşük**

**Davranışın tanımı.** Basis'in yakınsaması için güçlü teorik mekanizma vardır, ancak basis'in tek başına spotun hangi yöne gideceğini söylediği sonucuna ulaşılamaz. Yakınsama spotun perp'e, perp'in spota veya ikisinin ortak bir ara seviyeye hareket etmesiyle gerçekleşebilir. Teorik ve ampirik çalışmalar sapmaların arbitraj değeri taşıyabildiğini gösterse de bu, yönlü BTC/ETH edge'i değildir. citeturn11academia25turn11academia26

**Test kuralı taslağı.** Basis'i yön sinyali yerine volatilite ve kırılganlık özelliği olarak kullan. Yön modeli içinde basis seviyesi, basis değişimi ve basis'in fiyat hareketine tepki vermemesi ayrı özellikler olsun.

**Zayıflıklar.** Stablecoin farkı, endeks bileşimi, borsa riski ve funding saati sonuçları etkiler.

**Maliyet hassasiyeti.** Yönlü tek bacakta orta; gerçek yakınsama arbitrajında yüksektir.

**Kart Q — Likidasyon haritasındaki kümelerin fiyatı mıknatıs gibi çekmesi**

**Kanıt düzeyi: Düşük**

**Davranışın tanımı.** Likidasyon haritaları gerçek kullanıcı stop emirlerini değil, varsayılan kaldıraç ve geçmiş fiyat davranışından türetilen tahmini tasfiye bölgelerini gösterir. Tasfiye gerçekleştikten sonra elde edilen reported-liquidation verisi daha somuttur; Coin Metrics'in beş dakikalık ve saatlik liquidation buy/sell serileri buna örnektir. citeturn10search12

**Test kuralı taslağı.** Haritadaki bölgeye temasın gerçekleşme ihtimalini değil, temas sonrasındaki koşullu getiriyi ölç: bölgeye mesafe, OI değişimi, funding, spot CVD ve gerçekleşen liquidation birlikte modele girsin.

**Zayıflıklar.** Harita hesaplama yöntemi değişebilir; gerçek kaldıraç dağılımı bilinmez. Fiyatın sonradan kümeye gitmesi seçici örnekleme etkisi yaratabilir.

**Maliyet hassasiyeti.** Orta-yüksek; kümeye yaklaşırken volatilite ve slippage artabilir.

## Backtest tasarımı ve metodolojiye entegrasyon

Bu araştırmadaki hipotezlerin güvenilir biçimde test edilebilmesi için tek bir TradingView grafiği veya tek borsa verisi yeterli değildir. Gerekli veri katmanları şunlardır:

| Veri ailesi | Minimum sıklık | Kullanım |
|---|---:|---|
| BTC/ETH spot OHLCV | 1m veya 5m | 15m/1h mum üretimi, gerçek volatilite |
| Perpetual OHLCV | 1m veya 5m | Türev fiyatı ve kırılmalar |
| Spot ve perp bid/ask | Tick veya 1m | Spread ve gerçekçi execution |
| Open interest | 5m–15m | Pozisyon açılışı/kapanışı ayrımı |
| Funding ve predicted funding | Borsa özgü | Kaldıraç/sentiment rejimi |
| Perp–spot premium | 1m–5m | Basis sapması |
| Gerçekleşen liquidations | 5m | Kaskad tespiti |
| Spot ve perp trade flow/CVD | 1m–5m | Agresif alıcı/satıcı teyidi |
| Ekonomik olay takvimi | Olay zamanı | FOMC, CPI ve benzeri filtreler |
| Options expiry/OI | Saatlik veya günlük | Deribit settlement ve gamma bağlamı |

Coin Metrics'in resmî veri altyapısında market trades, OI, liquidation, funding, predicted funding, order book, quote, candle, contract price, implied volatility ve Greeks veri kümeleri bulunmaktadır. Bu, CoinGlass/CryptoQuant tabanlı görsel incelemelerin yanında daha tekrarlanabilir bir araştırma veri hattı oluşturmak için kullanılabilir. citeturn10search6turn11search8

Backtest aşağıdaki kurallara uymalıdır:

**Zaman ve veri standardizasyonu.** Ham veri UTC tutulmalı; Londra ve New York seansları timezone-aware takvimlerle oluşturulmalıdır. DST değişimlerinde sabit Türkiye saati kullanılmamalıdır. Borsalardan gelen mumlar kullanılmak yerine mümkünse trade verisinden ortak mumlar oluşturulmalıdır.

**Look-ahead kontrolü.** Funding, OI ve liquidation verisi ancak gerçek zamanda yayımlandığı anda kullanılmalıdır. Bir saatlik OI değişimi hesaplanırken saatin sonundaki veriyle saatin başında işlem yapılmamalıdır. FOMC takvimi önceden bilinebilir, fakat açıklamanın içeriği yayımlanmadan kullanılamaz.

**Maliyet modeli.** Her strateji en az şu senaryolarda çalıştırılmalıdır:

| Senaryo | Tek yönlü toplam execution varsayımı |
|---|---:|
| İyimser maker | Gerçek maker ücreti + yarım spread |
| Gerçekçi likit piyasa | 2–5 baz puan |
| Taker ağırlıklı | 5–10 baz puan |
| Stresli piyasa | 10–25 baz puan |
| Kaskad | 25–100 baz puan ve fill olasılığı |

Bu rakamlar piyasa hakkında sabit iddialar değil, hassasiyet testi için önerilen stres aralıklarıdır. Gerçek ücretler borsa, VIP seviyesi ve döneme göre tarihsel olarak uygulanmalıdır.

**Doğru eğitim/test ayrımı.** Önerilen minimum yapı:

- İlk dönem: parametre geliştirme.
- İkinci dönem: doğrulama.
- Son dönem: dokunulmamış out-of-sample test.
- Ek olarak altı aylık veya on iki aylık walk-forward.
- BTC'de geliştirilen parametreler ETH'ye doğrudan taşınmamalı; ETH bağımsız dış örneklem olarak da kullanılmalıdır.
- Borsa bazında sonuç verilmeli; birleşik fiyat yalnızca ek sağlamlık testi olmalıdır.
- Çok sayıda eşik taranıyorsa Deflated Sharpe Ratio, White Reality Check veya benzeri data-snooping düzeltmeleri kullanılmalıdır.

**Rejim matrisi.** Kartların birlikte kullanılmasında en anlamlı çerçeve şudur:

| Volatilite | Funding/OI | Likidasyon | Tercih edilecek hipotez |
|---|---|---|---|
| Düşük | Nötr | Düşük | Range mean reversion |
| Yükseliyor | Nötr | Düşük | Hacim teyitli breakout |
| Yüksek | OI yükseliyor | Düşük | Momentum; fakat kırılganlık artıyor |
| Yüksek | Funding aşırı | OI aşırı | Yeni giriş azalt; failure/reversal izle |
| Çok yüksek | OI sert düşüyor | Çok yüksek | Kaskad devamı, sonra exhaustion |
| FOMC/expiry penceresi | Herhangi | Herhangi | Olay modeli veya no-trade |
| Hafta sonu | Herhangi | Düşük | Daha sıkı likidite ve cross-venue teyidi |

Araştırmadan çıkan en savunulabilir öncelik sırası şöyledir:

1. **FOMC sonrası volatilite genişlemesi**, güncel ve sağlam bir olay etkisidir; öncelikle risk ve breakout filtresi olarak test edilmelidir. citeturn10search3
2. **Hacimle koşullandırılmış intraday momentum**, doğrudan yönsel edge adayları arasında en güçlü akademik temele sahiptir. citeturn9search0turn9search6
3. **Avrupa/ABD açılışı ve Deribit settlement saatleri**, yön değil fakat volatilite ve likidite rejimi açısından kalıcı görünmektedir. citeturn10search2turn12search1
4. **Funding ve OI**, tek başına long/short sinyali değil; yüksek kaldıraç ve yaklaşan volatilite filtresi olarak daha güvenilir kullanılmalıdır. citeturn11search0
5. **Likidasyon sonrası reversal**, ekonomik olarak makul ancak tek olay ve pratisyen kanıtına fazla bağımlıdır; en sıkı maliyet ve fill simülasyonu burada uygulanmalıdır. citeturn12search2turn12search6
6. **Mum sınırı anomalisi**, belgelenmiş olmasına rağmen en hızlı bozunabilecek ve maliyet tarafından yenilebilecek edge'dir. citeturn9search2

Bu nedenle ilk backtest portföyü, birbirine fazla benzeyen onlarca gösterge yerine dört bağımsız deney ailesinden oluşturulmalıdır: **hacim koşullu momentum**, **jump sonrası teyitli reversal**, **FOMC/seans volatilite kırılması** ve **funding–OI–liquidation rejim filtresi**. Böyle bir yapı, aynı bilgiyi farklı göstergeler üzerinden tekrar sayma riskini azaltır ve hangi edge'in gerçekten fiyat tahmini, hangisinin yalnızca risk filtresi olduğunu açık biçimde ayırır.
