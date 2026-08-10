# ADR-0045 — S-0006 katılım kompozisyonu ölçümü: reddedildi

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi (ölçüm kaydı)
- **İlgili:** Platform ADR-0006, Signal ADR-0043, ADR-0044, `docs/hypotheses/S-0006.md`

## Bağlam

S-0005'in reddinden (ADR-0043) sonra dördüncü yönsel aile ön-kaydedildi: katılımın bileşimi
(spot hacim payı vs perpetual hacim payı). Mekanizma iddiası, aynı fiyat hareketinin gerçek
varlık transferiyle mi yoksa sentetik kaldıraçla mı taşındığının hareketin niteliğini ele
verdiğiydi.

**Aday seçimi öncesinde ölçülebilirlik kontrolü yapıldı.** İlk düşünülen aile (FOMC/CPI olay
penceresi) Development penceresinde yalnız **21 olay** taşıyordu ve kartların 100 işlem
şartını yapısal olarak karşılayamazdı; **ön-kaydedilmeden elendi**. Bu bir sonuç dikizlemesi
değil örneklem kontrolüdür ve deneme sayacına girmemiştir.

## Ölçüm

Yetkili koşu `E-20260810-205747-1c4fb1`, `dataset_snapshot = 637104fbb080ac50…`.

| | `realistic` | `taker_heavy` |
|---|---|---|
| Kümülatif net getiri | **−61.63%** | **−78.34%** |
| Buy & Hold | −13.56% | −15.47% |
| Simple Trend | +6.69% | −12.80% |

715 işlem, `p = 0.4273`, fold tutarlılığı %39.3.

**Sonuç: REDDEDİLDİ** — her iki senaryoda negatif, baseline'ları aşamadı, `p ≥ 0.05`,
fold tutarlılığı `< %60`.

## Kararlar

### 1. Ters çevirme yapılmayacaktır

Sonuç yalnız negatif değil, hipotezin yönüyle **ters** çıkmıştır. "Öyleyse ters çevirelim"
çıkarımı açıkça reddedilir:

- Sonucu görüp yönü çevirmek ön-kaydın tamamını anlamsız kılar ve ADR-0007'de kayıtlı hatanın
  birebir tekrarıdır.
- `p = 0.4273` ilişkinin rastgeleden ayrışmadığını söyler; −%61.63'ün **işareti de** gürültü
  olabilir. Ters çevrilmiş bir kural, gürültüye uydurulmuş bir kural olurdu.
- Ters yönlü varyant yeni bir hipotez olarak da ön-kaydedilmeyecektir: sonucu görülmüş bir
  aileden türetilmiş olurdu (ADR-0004 §4 "sonuçları görülmemiş" şartı).

Aile kapanmıştır.

### 2. Ölçüm protokolü kopyalanmadı, paylaşıldı

`evaluate_s0006.py`, işlem/fold/baseline/kapı mantığını `evaluate_s0005.py`'den **import
eder**. İki aile aynı protokolle ölçülmelidir ki aralarındaki fark hipotezden gelsin, ölçüm
farkından değil. S-0003/S-0004'te bu mantık dosya başına kopyalanmıştı; yeni ailelerde
tekrarlanmıyor.

### 3. Kod ölçümden önce commit edildi

S-0005'in ilk koşusu scriptler commit edilmemişken yapılmış ve `invalid` işaretlenmek zorunda
kalınmıştı (`V-20260810-190041-e3f90a`). S-0006'da kod önce commit edildi, ağacın temizliği
doğrulandı, sonra ölçüldü. Sonuç: **`git_dirty = False`** — ADR-0044'ten sonra bu bayrağı
gerçekten anlamlı biçimde taşıyan ilk ölçüm.

### 4. Kırılganlık sorusu ayrıdır

Katılım bileşiminin 24 saatlik ufukta **yönsel** bilgi taşımadığı ölçülmüştür. Bu, aynı
büyüklüğün **kırılganlık** göstergesi olarak değeri hakkında hiçbir şey söylemez; o ayrı bir
soru ve ayrı bir ön-kayıt gerektirir. Faz 2 kırılganlık kolu bundan etkilenmez.

## Sonuçlar ve sınırlar

Yönsel skor tahtası: **4 aile denendi, 4'ü reddedildi** (S-0003, S-0004, S-0005, S-0006).

Runtime davranışı değişmez: `direction=null`, `directional_decision_allowed=false`, `WAIT`.
Bu ADR alpha iddiası taşımaz.

Dört redde rağmen ölçüm hattının kendisi güçlenmiştir: ön-kayıt disiplini, iki maliyet
senaryosu, üç baseline, purged walk-forward, çalışan temiz-ağaç kanıtı ve paylaşılan protokol
artık yerindedir. Bir sonraki aile için asıl darboğaz kod değil, **mekanizması gerçekten
bağımsız ve bugün ölçülebilir bir hipotez** bulmaktır; mevcut veri yüzeyinde bu havuz
daralmıştır. Order-book likidite asimetrisi gibi taze mekanizmalar yeterli canlı geçmiş
biriktiğinde açılabilir.
