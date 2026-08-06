# RADAR PLATFORM — DURUM VE DEVİR RAPORU

**Tarih:** 5 Ağustos 2026 · **HEAD:** `c7f10b2` · **Kapsam:** `radar-platform` monorepo
**Amaç:** Bir sonraki oturumun (insan veya ajan) sıfırdan bağlam kurmadan devam edebilmesi.

> **Bu belge tarihlidir.** Güncel olup olmadığını doğrulamak için:
> `git log --oneline c7f10b2..HEAD` — çıktı boş değilse bu rapor geridedir, `git log` ve
> `docs/HEDEFE-GELISTIRME-PLANI.md` esas alınır.

---

## 1. Tek paragrafta durum

Veri → PIT → snapshot → saatlik karar → outbox → sonuç zinciri uçtan uca çalışıyor ve
testli. İki yönsel hipotez (S-0003 funding uç noktası, S-0004 volatilite koşullu trend)
ön-kayıtlı protokolle ölçüldü ve **ikisi de reddedildi**. Bunun üzerine ürün v1
yeniden tanımlandı: **yön tahmini değil, kırılganlık/volatilite riski uyarısı**
(Platform ADR-0004). Şu an aktif iş, bu uyarının gerçekten öngörü taşıyıp taşımadığını
ölçecek olan **F-0001 kalibrasyon hipotezi** — kart donduruldu, makine kuruldu,
**ölçüm henüz koşulmadı**.

## 2. Ürün v1 nedir (ADR-0004)

Ürün yön söylemez. `direction=null` geçici bir durum değil, **ürün kararıdır**.
Çıktı: açıklanabilir kırılganlık, volatilite genişlemesi riski, veri güveni ve blocker
uyarısı. `WAIT`, nötr yön iddiası değil, yönün ölçülmediğinin ifadesidir.

**Yön yeniden açılabilir**, ama yalnız şu dördü birlikte sağlanırsa: sonucu görülmemiş
ve mekanizması önceki ailelerden bağımsız hipotez + ölçümden önce ayrı commit'li ön-kayıt
+ iki maliyet senaryosu + bağımsız venue kanıtı.

## 3. Çalışan ne var

| Katman | Durum |
|---|---|
| MCP toplama | Binance mark/funding/OI + spot OHLCV + basis + order-book spread/depth; PIT append-only |
| MCP geçmiş | 120 gün settled funding, ~30 gün saatlik OI, spot OHLCV backfill |
| MCP işletim | Scheduler (iki ritim), heartbeat kütüğü, veriden türeyen kapsama raporu, tek örnek kilidi |
| MCP skor | İki kırılganlık feature'ı (`funding_stress`, `oi_buildup`); yeterli-geçmiş kapısı fail-closed |
| Sözleşme | `contracts/decision-context/v1` — iki serviste ortak fixture ile doğrulanıyor |
| Signal karar | Saatlik deterministik `WAIT` kartı + değişmez ledger |
| Signal teslimat | Idempotent outbox → Telegram/console; fail-closed mod; webhook HMAC + replay koruması |
| Signal ölçüm | Karar sonuç değerlendiricisi (+1h/+4h/+24h, MFE/MAE, maliyet sonrası) |
| Araştırma | Purged walk-forward + embargo; üç baseline; DSR/PBO/hassasiyet/ablation kapıları |

**Kapılar:** MCP 226 test, signal 330 test, ruff iki tarafta temiz, açık PR yok.

## 4. Yapılmayan / sıradaki iş

1. **F-0001 ölçümü koşulmadı.** Kart `ÖN-KAYITLI — ÖLÇÜLMEDİ`. Makine hazır
   (Signal ADR-0021 OOF kalibrasyon, 0022 event-row, 0023 Coinbase bağımsız venue,
   0024 orkestratör). **Sıradaki asıl iş budur.**
2. **Toplayıcı çalışmıyor** — aşağıya bak, kalıcı veri kaybı üretiyor.
3. Kesinti bildirimi (alarm/Telegram operasyon kanalı) — Faz 3.
4. Faz 0'ın açık kalan tek maddesi: bağımsız onay kaydı + denetlenmiş Development
   reanalysis.

## 5. ⚠️ Açık operasyonel sorun: toplayıcı durmuş

`btc-radar-producer status` çıktısı (5 Ağu 2026): beş metriğin **hepsi 0 örnek**.

Bu üç oturumdur açık ve dönüşten sonra daha kritik: ürün v1 artık *canlı kırılganlık
uyarısı* ve F-0001 tam olarak o uyarının ileriye dönük kalibrasyonunu ölçecek.
`spot_perp_basis` ve `order_book_spread_bps` **`live_only`** — Binance tarihsel uç
sunmuyor, toplanmayan saat kalıcı kayıptır.

```powershell
cd services\btc-radar-mcp
.venv\Scripts\python.exe -m btc_radar.producer backfill --funding-days 120 --open-interest-days 30
.venv\Scripts\python.exe -m btc_radar.producer run --daemon `
  --context-root ..\radar-signal\var\decision-context --lock-file .\var\producer.lock
```

Kalıcı çözüm: Windows Task Scheduler, her dakika `run` (daemon'suz tek geçiş).

## 6. F-0001 ölçümünden önce cevaplanması gereken iki soru

**a) Lead time, hipotezin can damarı.** Kartın kendi risk bölümü kabul ediyor:
kırılganlık ve volatilite aynı şokun eşzamanlı belirtileri olabilir. Uyarı volatiliteyle
*aynı anda* geliyorsa ürün "fırtınadasın" diyen bir alet olur — doğru ama işe yaramaz.
Sonuçlara bakarken **ilk kontrol precision/recall değil, lead time dağılımı olmalı.**
Yüksek recall + sıfır lead time = başarısızlık.

**b) DSR deneme evreni belirsiz.** S-0003/S-0004 yönsel, F-0001 kalibrasyon hipotezi —
farklı soru uzayları. Aynı çok-deneme ceza havuzunda sayılacaklar mı? ADR-0019 net
söylemiyor. Ölçümden **önce** karara bağlanmalı, yoksa sonuç geldiğinde "ceza doğru mu
uygulandı" tartışması çıkar.

## 7. Bu projede oturmuş çalışma kuralları

Bunlar acı deneyimle öğrenildi; tekrarlamayın.

**Ön-kayıt iki commit'tir.** Kartı yaz/sıkılaştır → **ayrı commit** → sonra ölç. Tek
commit'te ikisi yapılırsa ajan sonucu görüp kartı ayarlayabilir. İnceleme sırasında
sıkılaştırma commit'inin içinde sonuç olmadığı ve o an kartın hâlâ `ÖLÇÜLMEMİŞ` dediği
**doğrulanır**. Sıkılaştırma meşrudur, gevşetme değildir; ölçümden sonra ikisi de yasak.

**Testler sentetik olur.** `user_data/` gitignore'lıdır; ona bağımlı test CI'da asla
geçmez (PR #12'de yaşandı). Aynı kalıp gerçek git geçmişine bağımlı testte de yaşandı
(PR #4). Test *mekaniği* doğrular, gerçek verdict'i değil.

**Registry append-only'dir.** Tarihî satır silinmez/yeniden yazılmaz. Düzeltme
`verdict_events.jsonl` olayıdır. Mükerrer koşu satırı DSR'ın N'ini bozar; aynı
(hypothesis, code_sha, dataset_snapshot) üçlüsü ikinci satır yazmaz — koruma mevcut.

**Paralel çalışma şerit ayrımıyla yürür.** MCP ↔ signal servisleri dosya düzeyinde
kesişmez, CI path filtreleri ayrıdır. Çakışma çıkan yerler her seferinde aynı üç dosya
oldu: `docs/HEDEFE-GELISTIRME-PLANI.md`, ilgili servisin `SPEC.md`, `.env.example`.
Feature PR'ları paylaşılan plan dosyasına dokunmasın; kutucuklar merge sırasında tek
elden güncellenir.

**ADR numarası tahmin edilmez.** Paralel dallarda iki kez çakıştı (MCP'de iki tane 0007,
signal'de 0011/0014 boşlukları). Klasöre bakıp en büyüğün bir fazlası alınır.

## 8. PR inceleme kontrol listesi

Kanıt üreten bir PR gelince sırayla:

1. CI yeşil mi? Kırmızıysa **sebebi ortam mı kod mu** — ayırt et.
2. Commit sırası: ön-kayıt/sıkılaştırma ölçümden önce mi?
3. Sıkılaştırma commit'i tek başına sonuç içeriyor mu? O an kart `ÖLÇÜLMEMİŞ` mi?
4. Tetikleyici / yön / ufuk ön-kayıttan **değişmiş mi**? (değişmişse test geçersiz)
5. Düzeltme commit'i ölçüm mantığına dokundu mu? Sayılar aynı mı kaldı?
6. Registry: tek satır mı, provenance bağlı mı, reddedilen de yazılmış mı?
7. Testler sentetik mi, gitignore'lı veriye bağımlı mı?
8. Locked OOS açılmış mı? (açılmışsa dur)
9. İki maliyet senaryosu da raporlanmış mı?
10. Verdict dürüst mü — "final/kabul edildi" etiketi kullanılmış mı?

## 9. Sayılarla kanıt defteri

Yeni protokolle ölçülmüş **2 geçerli deney** (S-0003, S-0004; ikisi de REDDEDİLDİ) +
1 baseline veri bakışı (S-0004 kartında ilan edildi). Eski S-0001/S-0002 satırları
registry'de duruyor ama 7'si `INVALID` işaretli, DSR evrenine girmez.

| Hipotez | Sonuç | realistic | taker_heavy | p |
|---|---|---|---|---|
| S-0003 funding uç reversal | REDDEDİLDİ | −%25,5 | −%42,1 | 0,41 |
| S-0004 volatilite koşullu trend | REDDEDİLDİ | −%67,5 | −%77,4 | 0,55 |
| F-0001 kırılganlık kalibrasyonu | ölçülmedi | — | — | — |

## 10. Değişmez kurallar (kod bunları zorluyor)

1. Gerçek emir yok, private API key yok, kişiselleştirilmiş tavsiye yok.
2. `direction` aktif profilde daima `null`.
3. Eksik/yetersiz veri nötr skora dönüşmez: blocker yazılır, context `unavailable` olur.
4. Look-ahead yasak: yalnız `available_at <= karar_anı` satırları kullanılır.
5. Maliyetsiz sonuç raporlanmaz: `realistic` **ve** `taker_heavy`.
6. Eşikler config'de, koda gömülmez; göreli yüzdelik kullanılır, mutlak sayı değil.
7. Locked OOS bir kez açılır; varsayılan kapalıdır.
8. Kanıt üreten iş `feature/` dalında + PR + bağımsız inceleme (signal kuralı 13).
