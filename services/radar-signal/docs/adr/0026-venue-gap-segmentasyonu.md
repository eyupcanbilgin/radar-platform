# ADR-0026 — Venue Gap Segmentasyonu

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** F-0001, Signal ADR-0022, ADR-0023

## Bağlam

Coinbase BTC-USD public saatlik API'sinde iki gerçek tarihsel kesinti doğrulandı: 25 Ekim
2025 16:00–20:00 UTC ve 8 Mayıs 2026 02:00–06:00 UTC için mum dönmüyor. Dar aralık tekrar
sorguları da aynı boşlukları verdi; pagination kusuru değil venue veri yokluğudur.

## Karar

1. Coinbase indiricisi iç gap'leri doldurmaz; özgün mumları yazar ve eksik saat/gap sayısını
   açık coverage olarak raporlar. Duplicate, eksik başlangıç/son ve açık mum hâlâ hatadır.
2. F-0001 venue etiketleyicisi seriyi yalnız ardışık birer saatlik segmentlere böler.
   Trailing ve ileri ufuk aynı segment içinde tam değilse karar saati etiketlenmez.
3. Segment öncesi tamamen settled, geçerli volatilite oranları sonraki segmentin geçmiş
   yüzdelik dağılımında kullanılabilir; eksik pencerenin kendisi hiçbir oran üretmez.
4. Gap aralıkları, eksik saat ve segment sayısı event-row ile nihai evidence artefaktına
   bağlanır. Eksik veri sakin/nötr olay sayılmaz.
5. Bu karar gerçek F-0001 metriği veya verdict içermez; ölçümden önce ayrı commit'tir.

## Sonuç

İki venue zorunluluğu korunurken birkaç saatlik açık venue kesintisi tüm çok-yıllı seriyi
geçersiz kılmaz. Yalnız matematiksel olarak tam pencereler ölçülür; coverage kaybı görünürdür.
