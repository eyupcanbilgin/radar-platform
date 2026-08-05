# ADR-0004 — Ürün v1 kırılganlık ve volatilite uyarısı odağı

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0003, MCP ADR-0005–0008, Signal ADR-0017–0020

## Bağlam

Platformun veri → PIT → snapshot → saatlik karar → outbox → sonuç zinciri çalışmaktadır.
Settled funding ve OI üzerinden gerçek, point-in-time kırılganlık gözlemi üretilebilmektedir.
Buna karşılık iki ayrı yönsel aile Development döneminde reddedilmiştir:

- S-0003 settled funding uç reversal: `realistic -25.5%`, `taker_heavy -42.1%`.
- S-0004 volatilite koşullu trend: `realistic -67.5%`, `taker_heavy -77.4%`.

Daha önce ölçülmüş seans ailesi de yönsel öngörü göstermemiş, esas olarak volatilite
zamanlaması kanıtı üretmiştir. Sonucu görülmüş aileyi yeni hipotez gibi ön-kayıt etmek veya
aynı mekanizmayı yeni eşiklerle tekrar denemek araştırma disiplinini ihlal eder.

## Karar

1. Ürün v1'in birincil çıktısı yön tahmini değil, açıklanabilir **kırılganlık, volatilite
   genişlemesi riski, veri güveni ve blocker** uyarısıdır.
2. Aktif runtime profili `direction=null`, `directional_decision_allowed=false` ve `WAIT`
   olarak kalır. `WAIT` nötr yön iddiası değil, yön ölçülmediğinin açık ifadesidir.
3. `decision-context/v1` şeması değişmez; mevcut null/kapalı yön semantiği yeni ürün profilini
   zaten taşır. Şemadaki yön alanları gelecekteki uyumluluk yüzeyidir, aktif özellik değildir.
4. Yönsel araştırma park edilir. Ancak sonuçları görülmemiş, ekonomik mekanizması önceki
   ailelerden bağımsız bir hipotez; ölçümden önce ayrı commit'li ön-kayıt; Development
   protokolü; iki maliyet senaryosu ve bağımsız venue kanıtı birlikte hazırsa yeniden açılır.
5. Faz 2, kırılganlık uyarısının olay etiketini ve kalibrasyonunu ölçer: ileri gerçekleşen
   volatilite/MAE, lead time, precision-recall, calibration, false-alarm, abstention ve veri
   kapsamı. Eksik sonuç sıfır veya sakin piyasa sayılmaz.
6. Yeni veri ailesi, yön açmak için değil, mevcut kırılganlık uyarısına point-in-time marjinal
   katkısı ablation ile gösterilirse eklenir. Eşikler config'de ve göreli yüzdelik kalır.
7. Gerçek emir, private API anahtarı, kişiselleştirilmiş tavsiye ve LLM'in canlı karar yetkisi
   kapsam dışı kalır.

## Sonuçlar

Çalışan ürün zinciri kanıtlanmamış alpha arayışına bağlı kalmaz. Kullanıcı, piyasanın hangi
yöne gideceği iddiası yerine kaldıraç/likidite baskısının arttığı, verinin yetersiz olduğu ve
oynaklık riskinin genişleyebileceği koşulları görür. Tarihî yönsel retler korunur; yeni eşik
aramalarıyla yeniden yorumlanmaz. Yön ancak bu ADR'deki yeniden-açma kapısını eksiksiz geçerse
ayrı bir ürün kararıyla değerlendirilebilir.
