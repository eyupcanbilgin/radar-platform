# RADAR Hedefe Geliştirme Planı

**Durum:** AKTİF · **Yeniden yazıldı:** 8 Ağustos 2026 (ADR-0006) · **Ürün sahibi:** Eyüpcan
**Tek aktif depo:** `radar-platform`
**Tamamlanmış faz geçmişi:** `docs/PLAN-ARSIV-2026-08.md`

## 1. Kuzey Yıldızı

> Çok kaynaklı piyasa verisini otomatik izleyen; yalnız ölçülmüş bir kurulum oluştuğunda
> açıklanabilir kırılganlık, volatilite genişlemesi riski, veri güveni ve blocker uyarısı
> üreten; yön ölçülmedikçe `direction=null`/`WAIT` kalan ve uyarılarının ileri sonuçlarını
> değişmez bir defterde ölçen kişisel piyasa risk karar-destek sistemi.

Kârlılık bir yazılım özelliği veya vaat değildir. Sistem gerçek emir göndermez; çıktılar
`DENEYSEL/PAPER` etiketi taşır.

## 2. Bağlayıcı kısıt

**Kesintisiz point-in-time geçmiş derinliği.** Projenin tek manşet metriği budur:

| Aile | Kaynak geçmişi | Config ihtiyacı | Bugün kesintisiz elde |
|---|---|---|---|
| `funding_stress` | `fundingRate` — 400+ gün çekilebilir | `min_span_days: 45` | **ölç ve buraya yaz** |
| `oi_buildup` | `openInterestHist` — ~30 gün sert saklama sınırı | `min_span_days: 14` | **ölç ve buraya yaz** |
| `spot_close` | backfill + canlı | — | **ölç ve buraya yaz** |
| `spot_perp_basis` | `live_only` | — | **ölç ve buraya yaz** |
| `order_book_spread_bps` | `live_only` | — | **ölç ve buraya yaz** |

Bir iş bu tabloyu iyileştirmiyorsa ikincildir. `oi_buildup` için duran her saat **kalıcı**
kayıptır: saklama penceresinden eski OI ancak biz sakladıysak vardır.

Kısıtın ürüne etkisi: `fragility_calibration.yaml` iki aileyi de zorunlu tutar ve zincir
fail-closed olduğu için ince aile düştüğünde derin aile de düşer, context `unavailable`
olur. Ayrıntılı teşhis ADR-0006'dadır.

## 3. Uçuşta olan tek ölçüm

**F-0002 — funding kırılganlığı sonrası volatilite genişlemesi (tek aile).**

| Kapı | Durum |
|---|---|
| Kart ön-kaydı (`feature/` dalı + PR + bağımsız inceleme) | ☐ |
| 400 günlük settled funding PIT backfill'i ve coverage kanıtı | ☐ |
| Ölçüm koşusu (ayrı commit; kart sıkılaştırmasıyla asla aynı commit'te değil) | ☐ |
| Registry satırı + verdict (ret dahil) | ☐ |

Kurallar: `direction` null kalır; eksik/yetersiz sonuç `unavailable`dır, sakin piyasa
sayılmaz; eşikler config'de ve göreli yüzdeliktir; Locked OOS kapalıdır; sonuç görülerek
hiçbir eşik değişmez. Tek aileye düşen hipotez daha zayıf bir iddiadır ve kart bunu açıkça
taşır.

**F-0001:** `ARŞİV — ÖLÇÜLEMEZ` (ADR-0006). Ret değildir; hiçbir kabul/ret metriği
üretmemiştir. Eşikleri dokunulmaz. Harici meşru tarihsel OI gelirse ayrı kararla açılır.

## 4. P0 — Toplayıcı sürekliliği

Bağlayıcı kısıtın tek gerçek kaldıracı. Faz 3'ten öne alındı.

- [ ] Kesinti bildirimi: toplayıcı durduğunda veya kapsama düştüğünde operatöre alarm.
- [ ] Bölüm 2 tablosunu veriden türeten tek komut; çıktısı bu dosyaya elle değil raporla girer.
- [ ] Forward context'lerin neden `unavailable` döndüğünü çalışan runtime'ın PIT'i üzerinde
      doğrula (teşhis: `oi_buildup` yetersiz-geçmiş kapısı).

## 5. Donduruldu

Aşağıdaki alanlar çalışır kabul edilir. Yeniden açılması somut bir işletim arızası gerektirir:
runtime supervision, launchd/plist üretimi, runtime lock, coverage reporter, import smoke,
teslimat kartı biçimi.

Ayrıca: **ölçüm kaydetmeyen ADR yazılmaz.** Faz 3 risk kapıları (`valid_until`, risk bütçesi,
korelasyon limiti, kill-switch'ler) doğrulanmış bir uyarı çıkana kadar ertelenmiştir — kapsam
dışı değil, sırası gelmemiştir. F-0001 forward defteri çalışmaya devam eder ama geliştirilmez;
kapsam sayacıdır, ölçüm aleti değildir.

## 6. Değişmez ürün ilkeleri

1. Gerçek borsa emri yoktur; execution ayrı ve gelecekteki bir karar kapısıdır.
2. LLM canlı yön, boyut veya emir kararı vermez.
3. `WAIT/NO-TRADE` birinci sınıf ve ölçülen bir çıktıdır.
4. Her karar `as_of`, `snapshot_id`, veri sürümü, kural sürümü ve gerekçeyle replay edilebilir.
5. Yönsel setup, rejim ve risk ayrı katmanlardır; rejim tek başına yön sinyali sayılmaz.
6. Yeni veri kaynağı yalnız point-in-time zincirine bağlanırsa ve marjinal katkısı ölçülürse
   eklenir.
7. Başarı; win-rate veya test sayısıyla değil maliyet sonrası beklenti, drawdown, kalibrasyon
   ve forward sapmayla ölçülür.
8. Locked OOS bir kez açılır; geliştirme sonucu hiçbir zaman final OOS diye sunulmaz.
9. Ürün v1 yön tahmini yapmaz; `direction=null` ölçülmemiş yönün tek doğru gösterimidir.
10. Yönsel araştırma parktadır (ADR-0004); yeniden-açma kapısı geçilmeden yeni yön denemesi yok.

## 7. Sıradaki kapılar

| Sıra | Kapı | Ön koşulu |
|---|---|---|
| 1 | Toplayıcı sürekliliği kanıtı | — |
| 2 | F-0002 ön-kaydı | 1 |
| 3 | F-0002 Development ölçümü | 2 + funding backfill coverage kanıtı |
| 4 | Uyarı kartını direction üretmeden ledger/outbox hattına bağla | 3 kabul ederse |
| 5 | Forward paper karantina (min 4 hafta AND 100 bağımsız karar AND 2 rejim) | 4 |
| 6 | Faz 3 risk kapıları ve kill-switch'ler | 5 |
| 7 | Kapsam genişletme (ETH replikasyonu → cross-venue → ...) | 6 |

Faz 0'ın açık kalan tek maddesi bu sıralamanın dışında durur ve F-0002 kabul alırsa
kapatılması zorunludur: incelenen signal commit'ine bağlı bağımsız onay kaydı ve temiz repo
sonrası denetlenmiş Development reanalysis.

## 8. Şimdilik yapılmayacaklar

- Gerçek emir veya trade yetkili API anahtarı
- Bütün kaynak linklerini collector'a çevirmek
- LLM'e yön/pozisyon/emir yetkisi vermek
- Alpha kanıtlanmadan dashboard, mobil uygulama veya kapsamlı ML platformu kurmak
- Geliştirme verisindeki en iyi sonucu "final" diye seçmek
- Kabul edilmiş setup olmadan rejim skorunu doğrudan pozisyona çevirmek
- Ölçüm ufkunu kısaltmayan yeni altyapı
