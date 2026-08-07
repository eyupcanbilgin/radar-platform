# RADAR Hedefe Geliştirme Planı

**Durum:** AKTİF · **Yeniden yazıldı:** 8 Ağustos 2026 (ADR-0006, ADR-0007 ile düzeltildi)
**Ürün sahibi:** Eyüpcan
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
| `funding_stress` | `fundingRate` — 2019'a kadar çekilebilir | `min_span_days: 45` | **ölç ve buraya yaz** |
| `oi_buildup` | canlı `openInterestHist` ~30 gün; **`data.binance.vision` günlük metrics paketleri 2020-09'dan itibaren** | `min_span_days: 14` | **ölç ve buraya yaz** |
| `spot_close` | backfill + canlı | — | **ölç ve buraya yaz** |
| `spot_perp_basis` | `live_only` | — | **ölç ve buraya yaz** |
| `order_book_spread_bps` | `live_only` | — | **ölç ve buraya yaz** |

Bir iş bu tabloyu iyileştirmiyorsa ikincildir.

Kısıtın niteliği (ADR-0007): veri **elde edilemez değil, içe aktarılmamıştır.** Doğru iş
beklemek ve alarm kurmak değil, kaynağı bağlamaktır. Toplayıcı kesintisi kalıcı kayıp
değildir; ertesi günün paketinden onarılabilir.

Not: `core/components.py` + `core/scoring.py` bir aile düştüğünde diğerinden **kısmi**
fragility yayımlar; MCP katmanında null olmaz. Rehin alma yalnız F-0001 protokol katmanında,
`features.required` ve ablation kapısı üzerinden gerçekleşir.

## 3. Uçuşta olan tek ölçüm

**F-0001 — kaldıraç kırılganlığı sonrası volatilite genişlemesi.** Statü: `VERİ İÇE AKTARIMI
BEKLİYOR`. Ret değildir; hiçbir kabul/ret metriği üretmemiştir. Eşikleri dokunulmaz.

| Kapı | Durum |
|---|---|
| `binance_vision_metrics` tarihsel OI içe aktarımı (ADR-0007 madde 4) | ☐ |
| Çakışma doğrulaması: paket serisi ≡ canlı uç nokta serisi (~30 gün) | ☐ |
| `f0001_readiness.py` kartından sıkı kapıyı düzelt (ADR-0007 madde 7) | ☐ |
| Readiness raporu `measurement_ready=true` | ☐ |
| Ölçüm koşusu + Registry satırı + verdict (ret dahil) | ☐ |

Kurallar: `direction` null kalır; eksik/yetersiz sonuç `unavailable`dır, sakin piyasa
sayılmaz; eşikler config'de ve göreli yüzdeliktir; Locked OOS kapalıdır; sonuç görülerek
hiçbir eşik değişmez. Çakışma doğrulaması geçmeden içe aktarılan veri ölçümde kullanılamaz.

**F-0002 (funding-only):** iptal (ADR-0007 madde 3). Gerekçesi birleşik hipotezin ölçülemez
sanılmasıydı; o gerekçe ortadan kalktı.

## 4. P0 — Tarihsel OI içe aktarımı

Bağlayıcı kısıtın tek gerçek kaldıracı.

- [ ] `binance_vision_metrics` provider + PIT içe aktarımı; yayın-anı semantiği mevcut
      backfill kalıbını izler (MCP ADR-0005). Yayın gecikmesi ölçülür, varsayılmaz.
- [ ] 5 dakikalık kovadan saatlik seriye indirgeme kuralı canlı uç noktayla aynı olmalı
      (saat sınırındaki örnek, ortalama değil); kural config'e yazılır.
- [ ] Çakışma doğrulaması geçmeden içe aktarım yok.
- [ ] Bölüm 2 tablosunu veriden türeten tek komut; çıktısı bu dosyaya elle değil raporla girer.
- [ ] Forward context'lerin neden `unavailable` döndüğünü çalışan runtime'ın blocker
      listesiyle doğrula — **teşhis henüz yok** (ADR-0006'nın teşhisi ADR-0007 ile çürüdü).

Ertelendi (aciliyetini kaybetti, kapsam dışı değil): toplayıcı kesinti bildirimi ve
barındırma tartışması.

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
| 1 | Tarihsel OI içe aktarımı | — |
| 2 | Çakışma doğrulaması + `f0001_readiness.py` onarımı | 1 |
| 3 | F-0001 Development ölçümü | 2 + readiness `true` |
| 4 | Uyarı kartını direction üretmeden ledger/outbox hattına bağla | 3 kabul ederse |
| 5 | Forward paper karantina (min 4 hafta AND 100 bağımsız karar AND 2 rejim) | 4 |
| 6 | Faz 3 risk kapıları ve kill-switch'ler | 5 |
| 7 | Kapsam genişletme (ETH replikasyonu → cross-venue → ...) | 6 |

Faz 0'ın açık kalan tek maddesi bu sıralamanın dışında durur ve F-0001 kabul alırsa
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
