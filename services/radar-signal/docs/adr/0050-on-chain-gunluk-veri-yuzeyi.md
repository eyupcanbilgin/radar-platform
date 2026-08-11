# ADR-0050 — Beşinci yönsel aile için on-chain günlük veri yüzeyi

- **Tarih:** 11 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Platform ADR-0006 (yönsel araştırmanın yeniden açılması), Platform ADR-0004 §4
  (mekanizma bağımsızlığı kapısı), ADR-0003 (Registry), S-0003, S-0004, S-0005, S-0006

## Bağlam

Ürünün hedefi LONG / SHORT / WAIT üreten bir karar-destek sistemidir (Platform ADR-0006).
Bugüne kadar dört yönsel aile ön-kaydedildi ve **dördü de reddedildi**:

| Aile | Mekanizma | Veri |
|---|---|---|
| S-0003 | Türev kaldıraç konumlanması → ortalamaya dönüş | Perp settled funding |
| S-0004 | Trendin volatilite rejimine koşullanması | OHLCV |
| S-0005 | Mekânlar arası (ABD/offshore) fiyat farkı | Coinbase + Binance spot |
| S-0006 | Hacmin finansman biçimi (spot payı ↔ perp payı) | Spot + perp hacim |

Ret oranı sorun değildir; ön-kayıt disiplininin çalıştığının işaretidir. Sorun şudur:
**bu dört aile, elimizdeki uzun geçmişli veri yüzeyini tüketti.** Yıllara giden serilerimiz
yalnız perp funding ve üç mekânın OHLCV'sidir. Bu yüzeyden çıkarılabilecek bağımsız
mekanizmalar denendi; kalanlar Platform ADR-0004 §4'ün bağımsızlık kapısından geçemez
(ör. OI–fiyat etkileşimi S-0003 ile aynı türev-konumlanma ailesindedir; mekânlar arası
**hacim** payı S-0005 ile aynı coğrafi-akış ailesidir).

Kısa geçmişli alternatifler de kapalıdır. Binance'in `/futures/data/` uçları (taker
alış/satış oranı, long/short hesap oranları) yalnız **son 30 günü** döndürür; Locked OOS
tasarımının gerektirdiği eğitim geçmişini taşımazlar. `live_only` metrikler (basis,
order-book spread) haftalarca canlı birikim bekler (kapsama oranı bugün ≈ 0.09).

Yani beşinci aile bir fikir eksikliğinden değil, **veri yüzeyi eksikliğinden** bloke.

11 Ağustos 2026'daki endpoint doğrulaması (MCP ADR-0013) bu boşluğun kapanabileceğini
gösterdi: bitcoin-data.com'un on-chain serileri anahtarsız çalışıyor ve **dört yıla**
gidiyor.

```
GET https://bitcoin-data.com/v1/sth-sopr
→ 1461 günlük satır, 2022-08-11 → 2026-08-10, tek istek
```

On-chain sahip davranışı (kâr realizasyonu / kapitülasyon) yukarıdaki dört mekanizmanın
hiçbiriyle akraba değildir: ne türev konumlanması, ne fiyat/volatilite rejimi, ne mekânlar
arası fiyat farkı, ne de hacmin finansman biçimi. Ölçtüğü şey zincir üzerinde **gerçekten
el değiştirmiş** coin'lerin maliyet tabanıdır.

## Kararlar

### 1. Bu paket yalnız veri yüzeyidir; hipotez değildir

İndirilen şey bir sinyal değildir. Hipotez kartı (S-0007) ve ölçüm **ayrı commit'lerde**
gelir; ön-kayıt sonuçtan önce dondurulur (ADR-0003 disiplini). Bu ADR bir yön iddiası
içermez ve `direction` hâlâ null'dur.

### 2. Look-ahead: iki ayrı zaman, tek kural

Günlük bir metrik gün kapanmadan var olamaz. Her satır iki zaman taşır:

- `event_time_utc` = D+1 00:00Z — değerin özetlediği dönemin sonu.
- `available_at_utc` = `event_time_utc` + `PUBLICATION_LAG_HOURS`.

Dosya bilinçli olarak **`date` kolonu taşımaz.** OHLCV dosyalarındaki tanıdık ad burada
bulunsaydı, PIT filtresini o kolona kuran ilk okuyucu sessizce look-ahead açardı. Manifest
bunun yerine zaman kolonunu tanır (`TIME_COLUMNS`); dosya adını değiştirmez.

### 3. Yayın gecikmesi cömert seçilir ve sonuca göre daraltılamaz

`PUBLICATION_LAG_HOURS = 24`. 11 Ağustos 11:47Z'de `d = 2026-08-10` satırı mevcuttu; yani o
gün için gerçek gecikme ≤ 11s47dk idi. Tek gözlem bir dağılım değildir, bu yüzden onun iki
katından fazlası donduruldu.

Hata payı bilinçli olarak **sinyali zayıflatan** yöne bırakılmıştır: ters yön look-ahead
olur ve ölçümü geçersiz kılardı. Bu sabit, ölçüm sonucu görüldükten sonra **daraltılamaz** —
daraltmak, sonucu gördükten sonra kuralı gevşetmek olurdu. Yalnız yayın gecikmesini ayrıca
ön-kaydedilmiş bir karakterizasyon ölçümüyle değiştirilebilir.

### 4. Sınır `available_at` üzerine uygulanır

`--end` kesimi gün üzerinden değil kullanılabilirlik üzerinden yapılır. Gün üzerinden
kesilseydi Locked OOS sınırından hemen önceki güne ait ama sınırdan **sonra** doğan satır
eğitim dosyasına girer ve kilidi içeriden delerdi. Test bunu açıkça korur.

### 5. Eksik veri sıfır değildir

Sayıya çevrilemeyen değer, eksik alan, bozuk gün biçimi, mükerrer gün ve boş seri
**yükselir**; sessizce 0'a veya boş dosyaya düşmez. Takvimde atlanan günler doldurulmaz,
`coverage.gaps` içinde raporlanır.

## Kanıt

Sentetik testler (`tests/test_download_onchain_daily.py`, ağa çıkılmaz): satır kendi gününde
kullanılabilir olamaz · kullanılabilirlik gün kapanışı + dondurulmuş gecikmedir · sınır
kullanılabilirlik üzerine kesilir (gün üzerinden kesilseydi `2026-08-03` satırı Locked OOS
dosyasına girerdi) · takvim boşluğu raporlanır, doldurulmaz · yanıt sırası ne olursa olsun
zamana göre sıralanır · mükerrer gün, parse edilemeyen değer, eksik alan, bozuk gün biçimi,
boş seri ve her şeyi dışlayan sınır fail-loud.

Manifest testleri: OHLCV dosyaları `date` kolonunu kullanmaya devam eder · on-chain seri
`event_time_utc` ile indekslenir (`available_at_utc` kullanılsaydı manifest aralığı veriyi
olduğundan yeni gösterirdi) · bilinen zaman kolonu taşımayan dosya fail-loud.

Canlı indirme (11 Ağu 2026): **1452 gün, 2022-08-11 → 2026-08-01, sıfır boşluk.** Son gün
`2026-08-01`'dir çünkü `2026-08-02` satırı tam Locked OOS sınırında (`2026-08-04T00:00Z`)
kullanılabilir hâle gelir ve dışlayıcı sınır onu dışarıda bırakır — kilit çalışıyor.

`MANIFEST-20260811` yeni dosya olarak üretildi; 10 Ağustos manifestleri (dört Registry
satırının işaret ettiği kanıt) el değmeden duruyor.

## Sonuçlar ve sınırlar

Bilinçli olarak **hâlâ yok**:

- **Yön iddiası.** Bu paket bir hipotez değildir; S-0007 ön-kaydı ayrı commit'tir.
- **Saatlik granülarite.** Seri günlüktür. 24 saatlik ufukla tutarlıdır ama saat içi bir
  yönsel kural bu veriden türetilemez.
- **Revizyon geçmişi.** Uç, geçmiş bir günün değerinin sonradan düzeltilip düzeltilmediğini
  söylemez. Bugün indirilen seri bugünkü hâlidir; geçmişteki bir koşunun gördüğü değerle
  aynı olduğu **varsayılamaz**. Manifest hash'i en azından hangi hâlin kullanıldığını mühürler.
- **Tek metrik.** Yalnız STH-SOPR indirildi. Diğer on-chain seriler aynı indiriciyle
  (`--path`, `--value-key`) gelir; her biri bütçeden bir istektir (8/saat, 15/gün).
