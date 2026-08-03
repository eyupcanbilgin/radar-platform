# S-0002 Bağımsız İncelemesi — Claude Code

**Tarih:** 4 Ağustos 2026 · **Rol:** İncelemeci (ADR-0004; yazar: Antigravity) · **Dal:** `feature/s-0002`
**Hüküm:** Bu koşu Kart A'nın **GEÇERSİZ** bir testidir — ret gerekçesi ölçüm hatasına dayanıyor.

---

## Özet

Ret kararının dayandığı üç sayı da ölçüm artefaktıdır:

1. Geliştirme dönemindeki **−89.9%** stratejinin performansı değil, cüzdanın tek stake birimine (≈1000 USDT) inip işlem açamaz hale gelmesidir. Üç senaryonun aynı sayıda toplanması bunun kanıtıdır.
2. Zararın **%75–83'ü komisyon+kaymadır**; brüt zarar çok daha küçüktür (−0.33/işlem).
3. Brüt zararın kendisi de **yanlış çıkış kuralıyla** üretilmiştir: Kart A'nın "1 ATR zarar durdurma"sı, her mumda sıkışan 1 ATR **trailing** stop olarak kodlanmış; işlemlerin %86.6'sı ortalama **16.5 dakikada** kesilmiş. Kart A'nın hedeflediği 4 mumluk ufka ulaşabilen 428 işlem **brüt +3.00/işlem kâr** etmiştir.

Ayrıca Kart A'nın 6 kuralından **3'ü kodda karşılığını bulmamıştır** (saat-dilimi koşullaması, 60 gün penceresi, funding/premium filtresi).

---

## Kanıtlar

### 1. Sermaye tükenmesi (tabana vurma) — DOĞRULANDI

| Koşu | İşlem | Son bakiye | Son işlem | Dönem sonu |
|---|---|---|---|---|
| DEV realistic | 4599 | 1009.4 | 2025-09-28 | 2026-02-03 |
| DEV taker_heavy | 3231 | 1006.1 | 2025-03-12 | 2026-02-03 |
| DEV stressed | 1885 | 1006.8 | 2024-09-13 | 2026-02-03 |

`dry_run_wallet=10000`, `stake_amount=1000` (sabit notional). Cüzdan ≈1 stake birimine inince yeni işlem açılamıyor; kayıp **yapısal olarak −%90'da tavanlıyor**. Aylık işlem sayısı çöküşe kadar düz (≈200/ay), sonra sıfır — sönüm değil, uçurum.

Maliyet monotonluğu **kaybolmuş değil**, terminal getiride değil **iflas hızında** görünüyor: 17 ay → 11 ay → 4 ay.

### 2. Maliyet senaryosu uygulanmış — ŞÜPHE ÇÜRÜTÜLDÜ

Registry `effective_fee` ↔ backtest `fee_open`: 0.00085 / 0.00125 / 0.00225 — üçü de birebir eşleşiyor.

OOS'ta üç senaryonun da 1311 işlem üretmesi **tutarsızlık değil, doğru davranıştır**: OOS'ta bakiye tabana vurmuyor (7118 / 6106 / 3576 > 1000), dolayısıyla aynı sinyal kümesinin tamamı fonlanabiliyor. Brüt P&L de üç senaryoda neredeyse aynı (−734 / −746), yalnız maliyet değişiyor. Geliştirmede sayıların farklı olması ise tam da tabana vurma etkisidir.

### 3. Sinyal frekansı: mantık doğru, eşikler geçirgen — KISMEN DOĞRULANDI

Koşullar doğru AND'lenmiş (ölçüm, 2024-01 → 2026-02, 72381 bar):

| Koşul | Tetiklenme |
|---|---|
| K1 getiri rank ≥ %80 | %19.85 |
| K2 hacim ≥ 1.25× medyan | **%38.61** |
| K3 1h aralık kırılımı | %12.80 |
| K1&K2&K3 (long) | %4.68 |
| Toplam giriş sinyali | 9.12/gün |

Gevşek bağlama YOK. Sorun K2'nin fiilen filtre olmaması (%38.6 geçirgenlik) — sebebi 4. maddedeki eksik saat-dilimi koşullaması.

### 4. Kart A uyumu — 6 kuralın 3'ü eksik/sapmış

| # | Kart A kuralı | Kod | Durum |
|---|---|---|---|
| 1 | Getiri, **aynı saat diliminin** 60 günlük dağılımında ≥%80 | Düz `rolling(1920)` rank, saat koşullaması yok, 20 gün | ✗ SAPMA |
| 2 | Hacim, **aynı saat diliminin** rolling medyanının ≥1.25× | Düz `rolling(1920).median()` | ✗ SAPMA |
| 3 | Kapanış önceki 1h aralığın dışında | `close > high.shift(1).rolling(4).max()` | ✓ |
| 4 | **Funding ve perp-spot farkı 90 günlük dağılımın aşırı %5'inde OLMASIN** | **YOK** | ✗ EKSİK |
| 5 | En fazla 4 mum taşıma | `holding_candles=4` | ✓ |
| 6 | Çıkış: 2 mum kırılımı / **1 ATR stop** / 4 mum zaman | 2 mum ✓, zaman ✓, ama stop **trailing** | ✗ SAPMA |

Ölçüm: saat-dilimi koşullamasıyla üretilen sinyallerin yalnız **%76.5'i** koddaki sinyallerle örtüşüyor — dörtte biri farklı bar. Funding filtresi barların **%6.0'ını** elemeliydi (90 günlük dağılım, gerçek funding verisiyle ölçüldü); perp-spot bacağı için spot veri hiç indirilmemiş.

**Sonuç:** Bu, Kart A'nın testi değil, "1 ATR trailing stop'lu hacim-teyitli kırılma" adlı başka bir stratejinin testidir.

### 5. Kıyas tabanı — ŞÜPHE ÇÜRÜTÜLDÜ (bir kayıtla)

S-0001 ile S-0002 aynı `config.dryrun.json` üzerinde: `dry_run_wallet=10000`, ortalama stake ≈960, `max_open_trades` etkin 1, `leverage=1.0`, güvenlik ağı stop −%10. Taban aynı.

`atr_stop_mult` farkı (2.0 → 1.0) strateji parametresidir, taban değil — meşru. Ancak **kıyasın kendisi geçersiz**: S-0002 geliştirme döneminin son 4 ayında hiç işlem yapmamış (cüzdan bitmiş), S-0001 tüm dönemi işlemiş. Farklı efektif test süreleri "toplam getiri %" ile kıyaslanamaz.

### 6. Her iki strateji de trailing-stop makinesi — DOĞRULANDI

| Çıkış | S-0002 DEV | Brüt/işlem | Ort. süre |
|---|---|---|---|
| trailing_stop_loss | %86.6 | −0.537 | 16.5 dk |
| time_exit | %9.3 | **+3.000** | 60.0 dk |
| stop_loss (−%10 ağ) | %2.7 | −3.877 | 6.4 dk |
| 2 mum yapısal kırılım | **%1.4** | −2.5 civarı | ~45 dk |

Kart A'nın **birincil çıkış kuralı (yapısal kırılım) işlemlerin yalnız %1.4'ünde** çalışabilmiş. S-0001'de de tablo aynı yönde: %96.9 trailing stop. İki strateji de fiilen aynı çıkış mekanizmasını test ediyor.

**Kritik gözlem:** Kart A'nın öngördüğü ufka (4 mum) ulaşabilen işlemler brüt **+3.00/işlem**, net **+586 USDT** kâr etmiştir. Hipotezin sinyali kesilmeden önce ifade edilebildiği tek altküme kârlıdır.

---

## Süreç ve disiplin bulguları

| # | Bulgu | Dayanak |
|---|---|---|
| S1 | 7 koşunun tamamı `git_dirty: True` ile kaydedilmiş; çalışma hiç commit'lenmemiş | registry provenance |
| S2 | Kart "Locked OOS" diyor ama kirli ağaçtan üretilmiş → CLAUDE.md kural 7 ile çelişiyor | S1 + kart satır 48-51 |
| S3 | **Locked OOS bir kez açıldı ve yandı.** Düzeltilmiş S-0002 aynı OOS'ta yeniden koşulamaz (kural 7) | kural 7 |
| S4 | Registry'de 7 koşunun `verdict`'i "pending" — ret kayda geçmemiş | registry |
| S5 | Hipotez kartı "aynı UTC saatindeki dağılım" diyor, kod bunu yapmıyor — kart kodu yanlış tarif ediyor | kart satır 13 ↔ kod satır 73-81 |
| S6 | 60 gün → 20 gün daralması sessiz uyarlama; ADR/SPEC notu yok (CLAUDE.md oturum akışı 2) | plan ↔ kod |
| S7 | S-0002 için birim/sözleşme testi yazılmamış (DoD-1) | `tests/` |
| S8 | DSR uygulanmamış (CR-1). Ret kararında zorunlu değil ama kartta belirtilmeli | kart |
| S9 | A/B/C kıyası (CR-3) yapılmamış — rejim/karartma katmanları henüz bağlı değil, bilinen boşluk | CR-3 |
| S10 | Registry `pairs` alanı taşımıyor; BTC/ETH koşuları kayıttan ayırt edilemiyor | **bt.py eksiği — yazar değil incelemeci kaynaklı (İ-3'te ben yazdım)** |

`ruff` temiz, `pytest` 110 yeşil, `lookahead-analysis` ve `recursive-analysis` temiz — kabul kapılarının çalışan kısmı sorunsuz.

---

## ADR-0004 değerlendirmesi

**Kabul edilebilir; ilke doğru.** Yazar ≠ incelemeci ayrımı SPEC §5 ve CR-001/CR-6(5) ile tutarlı. Üç düzeltme gerekiyor:

1. **Bağlayıcı sonuçlar CLAUDE.md'ye taşınmalı.** ADR'nin "main'e doğrudan commit yasak" kuralı yalnız ADR'de duruyor; yalnız CLAUDE.md okuyan bir oturum bunu görmez.
2. **Numaralandırma belirsiz.** ADR "§3 Kural 3" diyor; CLAUDE.md'de hem "Değiştirilemez kurallar 3" (global normalizasyon yasağı) hem "Oturum akışı 3" var. Değişen ikincisi — ADR bunu açıkça yazmalı.
3. **Kabul kapıları listesi eksik.** `lookahead/recursive/pytest/ruff` bu vakadaki hiçbir hatayı yakalayamazdı. Eklenmesi gerekenler: **hipotez kartı ↔ kod uyum denetimi**, **registry verdict kaydı**, **temiz ağaçtan koşu zorunluluğu**, **sermaye tükenmesi kontrolü**.

CLAUDE.md oturum akışı 3'ün yeni metni ("Görev başına tek yazar; yazar ≠ incelemeci") **doğru ve yerinde** — değiştirilemez kurallara dokunulmamış, kapsam korunmuş.

---

## Düzeltme önerileri (uygulanmadı)

**Ölçüm geçerliliği — geri kalan her şeyden önce**

1. `stake_amount`'ı sabit notional yerine **cüzdan yüzdesi** yap (ör. `unlimited` + `tradable_balance_ratio`, ya da %2-5 risk). Sabit 1000 stake, düşen cüzdanda oran olarak büyüyen bahis demektir ve −%90 tavanını üretir.
2. Backtest raporlarına **sermaye tükenmesi kontrolü** ekle: son işlem tarihi dönem sonundan anlamlı erken ise koşuyu "GEÇERSİZ — sermaye tükendi" damgala. Bu, sessizce yanlış okunan bir sonucu imkânsız kılar.
3. Kıyas metriğini toplam getiri %'den **işlem başına brüt/net beklenti**ye çevir; farklı efektif süreli koşular ancak böyle kıyaslanır.

**Kart A'ya sadakat**

4. Stop'u Kart A'nın dediği gibi **girişten sabit 1 ATR** yap (trailing değil). En düşük maliyetli ve en yüksek etkili tek değişiklik bu.
5. Saat-dilimi koşullamasını ekle (`groupby(hour)` üzerinde rolling rank ve medyan) ve pencereyi 60 güne çıkar; freqtrade `startup_candle_count` maliyeti kabul edilemezse **gerekçeyi ADR'ye yaz** (sessiz daraltma yok).
6. 4. koşulu (funding + perp-spot premium, 90 günlük dağılımın aşırı %5'i dışında) ekle. Funding verisi zaten inik; spot bacağı için `BTC/USDT` spot indirmek gerekiyor. `available_at ≤ karar_anı` kuralı (CR-3/P0-1) burada zorunlu.

**Süreç**

7. Çalışmayı commit'le; koşuları **temiz ağaçtan** tekrarla. `provenance.git_dirty=True` olan koşu "final" etiketi alamaz.
8. Registry'ye `pairs` alanı ekle (bt.py — benim eksiğim) ve `verdict`'i koşu sonrası güncelleyecek bir yol aç.
9. Hipotez kartını koda uydur (ya da kodu karta) — ikisi çelişemez. Bu denetimi CI'ya taşımak mümkün.
10. **Locked OOS burned.** Düzeltilmiş sürüm S-0002b/S-0006 olarak yeni kimlikle ele alınmalı ve 2026-02→08 dönemi artık development sayılmalı; yeni locked-test için ileri tarihli bir pencere ayrılmalı. Bu, düzeltme yapılmasa bile geçerli.

**Sıralama önerisi:** 1+4 (sizing + sabit stop) → tekrar koş → sonuç hâlâ negatifse 5+6 ile Kart A'ya tam sadakat → yine negatifse ret **artık gerçek bir rettir**.
