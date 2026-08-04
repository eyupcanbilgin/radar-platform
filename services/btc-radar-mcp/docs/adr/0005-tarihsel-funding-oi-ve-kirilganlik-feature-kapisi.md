# ADR 0005 — Tarihsel funding/OI birikimi, yeterli-geçmiş şartı ve kırılganlık feature'ları

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0004, Platform ADR-0003, `decision-context/v1`, Hedefe Geliştirme Planı Faz 1

## Bağlam

ADR-0004 gerçek Binance verisini PIT'e taşıdı ama yalnız **anlık** gözlemleri topluyordu.
Anlık bir değerden "funding aşırı" demek mümkün değildir: SPEC §5.1 kuralları göreli eşik
(rolling percentile / z-score) ister, göreli eşik ise geçmiş dağılım ister. `signal_rules.yaml`
boş kaldığı sürece `direction`, `fragility` ve rejim üretimi bilinçli olarak kapalıydı.

Bu paketin sorusu şudur: **kırılganlığı ölçmeye yetecek geçmişi nasıl dürüstçe biriktirir ve
"yeterli geçmiş" şartını nasıl uygulanabilir hâle getiririz?**

## Kararlar

### 1. Geçmiş veri ayrı bir provider ve ayrı metrik adlarıyla toplanır

`BinanceFuturesHistoryProvider` iki anahtarsız public ucu okur:
`/fapi/v1/fundingRate` → `funding_rate_settled`, `/futures/data/openInterestHist` (period=1h)
→ `open_interest_1h` + `open_interest_value_1h`.

`premiumIndex`'in `lastFundingRate` alanı **açık dönemin yürüyen tahminidir**, settle olmuş
ödeme değildir. İkisini tek metrik adı altında toplamak, yüzdelikleri tahmin ile gerçekleşme
karışımı bir dağılımdan hesaplamak olurdu. Bu yüzden metrik adları ayrıdır.

### 2. Backfill satırının yayın anı borsanın yayın anıdır, bizim koştuğumuz an değil

Geçmiş satırlar `available_at = event_time + publication_lag_seconds` ile yazılır
(lag config'den gelir, kodda sabit değildir; şu an 60 sn).

- `available_at = retrieved_at` seçilseydi backfill edilmiş geçmiş, geçmiş bir `as_of` için
  hiç görünmezdi ve rolling percentile hesaplanamazdı.
- Gecikmenin sıfırdan büyük olması, tam saatte damgalanmış bir kovanın **aynı saatin**
  kararına girmesini engeller (14:00 kovası 14:00 kararında kullanılamaz, 13:00 kullanılır).
- "O gün gerçekten ayakta mıydık" bilgisi kaybolmaz: `ingested_at` ve ayrı `provider` adı
  (`binance_futures_history`) canlı gözlemle backfill'i ayırır. Backfill, kesintisiz canlı
  işletim kanıtı olarak **sunulamaz**.

### 3. Uçların sayfalama davranışı ölçülerek yazıldı, belgeden kopyalanmadı (4 Ağu 2026)

| Uç | Davranış | Sonuç |
|---|---|---|
| `fundingRate` | `startTime` ileri yönlü çalışır, limit ≤1000, 400 gün geriye erişilebilir | İleri sayfalama; 120 gün tek istekte gelebiliyor |
| `openInterestHist` | `startTime` tek başına **yok sayılır**, pencerenin kuyruğu döner; limit ≤500; ~30 günden eski `startTime` → `-1130` **hata** | `endTime` ile geriye sayfalama; retention hatası `HistoryWindowError`'a çevrilir |

30 günlük saklama sınırı, planın "OI toplayıcısını sürekli çalıştır" maddesinin gerekçesidir:
o pencerenin ötesindeki geçmiş **yalnız kendi depomuzda** var olabilir. Bu yüzden `collect`
her koşuda en yeni geçmiş sayfalarını da yazar.

### 4. Yeterli geçmiş şartı bir feature özelliğidir ve fail-closed'dur

Her feature config'inde `min_samples`, `min_span_days`, `max_gap_seconds` ve
`expected_period_seconds` bulunur. Şart sağlanmazsa feature **üretilmez**; nedeni etiketlenir
(`no_history`, `insufficient_samples`, `insufficient_span`, `history_gap`,
`missing_change_window`, `stale`) ve context'e `feature_unavailable:<feature>:<neden>`
blocker'ı olarak yazılır. Eksik geçmiş sessizce nötr bir skora dönüşmez.

Bu sayılar **tuning sonucu değildir**; ölçüm yapılabilmesi için gereken tabanlardır. 11
örnekten "97. yüzdelik" demek ölçüm değil süslemedir.

### 5. İlk iki feature yalnız kırılganlık ölçer; yön üretmez

- `funding_stress`: settle funding'in 90 günlük **mutlak** dağılımdaki yüzdeliği. Mutlak
  alınır çünkü aşırı negatif funding de (kalabalık short) kırılganlıktır.
- `oi_buildup`: saatlik OI **notional**'ının 24 saatlik göreli değişiminin mutlak yüzdeliği.
  Notional kullanılır; kontrat adedi fiyat hareketiyle kaldıraç değişimini gizleyebilir.

Yüzdelik, ara değer üretmeyen midrank ampirik CDF'tir (eşitlikler yarıya bölünür); replay
bit-bit eşitliği buna dayanır. 24 saatlik değişimde eş kovası olmayan nokta **atılır**:
eksik kova "değişim sıfırdı" demek değil, "o değişimi bilmiyoruz" demektir.

### 6. `d=None` yön iddiasının yokluğunu taşır

`ScoreComponent.d` artık `None` olabilir ve bu bileşen yön paydasına hiç girmez. Kabul edilmiş
bir setup yokken `d=0` yazmak "yönü ölçtük, nötr çıktı" iddiası olurdu. Hiçbir bileşen yön
iddia etmiyorsa `direction` `null` kalır ve `direction_rules_unavailable` blocker'ı yazılır.
Sonuç: **fragility gerçek bir sayı, direction hâlâ null, yönsel karar hâlâ kapalı.**

### 7. Kanıt snapshot'a bağlanır, sözleşme değişmez

`RegimeSnapshot.evidence` alanı (feature_version `0.3.0`) örneklem sayısı, kapsanan süre,
en büyük boşluk, tazelik ve yüzdeliği değişmez kayda bağlar; içerik hash'ine dahildir. Eski
`0.1.0`/`0.2.0` kayıtları kendi hash sözleşmeleriyle doğrulanmaya devam eder.

`decision-context/v1` **değişmedi**: kanıt MCP tarafında snapshot'ta durur, context ise
`snapshot_id` + `content_hash` ile ona bağlıdır. Böylece iki servisi ilgilendiren bir sözleşme
sürümü açmadan denetlenebilirlik sağlanır.

### 8. Girdi digest'i kullanılan geçmişin tamamını kapsar

`snapshot_id` artık yalnız `as_of` satırlarından değil, feature'ların okuduğu tüm PIT
satırlarından türer. Aksi hâlde farklı geçmişler aynı kimlikle farklı fragility taşıyabilir ve
değişmezlik denetimi gerçek bir koruma olmaktan çıkardı.

## Sonuçlar ve sınırlar

Canlı doğrulama (4 Ağustos 2026): 120 günlük funding (360 settlement) ve 31 günlük saatlik OI
(744 kova) toplandı; `2026-08-04T14:00Z` için `fragility=0.0`, `direction=null`,
`confidence=25`, blocker `direction_rules_unavailable` yayınlandı. `2026-07-05T00:00Z` için
OI geçmişi 9 saat olduğundan `feature_unavailable:oi_buildup:missing_change_window` blocker'ı
yazıldı — kapı gerçek veriyle de çalışıyor.

Bilinçli olarak **hâlâ yok**:

- **Yön kuralı.** Kabul edilmiş setup olmadan açılmayacak.
- **Rejim sınıflandırması.** Tek katman (derivatives, ağırlık 0.25) güveni 25'te bırakıyor;
  eşik 55. §6 tablosu çok katmanlı kapsam ister, o yüzden etiket `veri_yetersiz` kalıyor.
- **Interaction kuralları.** Kırılganlık formülünde bağımsızlık terimi (u) yoktur; aynı iki
  feature'ı bir de etkileşim kuralında saymak skoru doğrudan şişirirdi. Önce CR-002 P1-1'in
  iki kademeli toplaması gerekir.
- **Scheduler / process supervision.** `collect` ve `backfill` hâlâ elle veya dış zamanlayıcı
  ile çağrılır; kesintisiz işletim kanıtı bir sonraki iştir.
- **Kısmi kapsamda kırılganlık ölçeği.** Tek feature ölçülebiliyorsa fragility yine 0-100
  ölçeğinde raporlanır; eksik kapsam **fragility'yi değil güveni** düşürür (SPEC §5.1). Yönsel
  kullanım zaten blocker'larla kapalıdır.

Bu paket "kırılganlık gözlemi ve yeterli-geçmiş kapısı hazır" demektir; "rejim analizi hazır"
veya "yön sinyali hazır" demek değildir.
