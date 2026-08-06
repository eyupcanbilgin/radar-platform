# RADAR PLATFORM — DURUM RAPORU

> **⚠️ GEÇERSİZ / TARİHÎ KAYIT.** Bu rapor `c32057f` dönemini anlatır ve o günün
> fotoğrafı olarak korunmuştur. Güncel durum: [`DURUM-RAPORU-2026-08-05.md`](DURUM-RAPORU-2026-08-05.md).
> Aradaki 45+ commit bu belgede yoktur; buradaki hiçbir satır bugünkü durumu tarif etmez.

**Tarih:** 4 Ağustos 2026 · **Hazırlayan:** Claude Code (incelemeci rolü) · **Kapsam:** `radar-platform` monorepo
**Yöntem:** Yalnız tespit. Bu rapor için hiçbir kod/config değiştirilmedi.
Emin olunmayan satırlar **[?]** ile işaretlidir.

---

## 1. DEPO YAPISI

**Konum:** `C:/Users/TKA/projeler/radar-platform` · **Toplam commit:** 36 · **HEAD:** `c32057f`

```
radar-platform/
├── CLAUDE.md (23 satır — yalnız yönlendirici), README.md, SECURITY.md, Makefile, .gitattributes
├── contracts/            1 dosya  (README; henüz şema taşınmamış)
├── docs/                 2 dosya  (architecture.md + adr/0001)
├── scripts/              1 dosya  (check_repo_policy.py)
├── .github/workflows/    4 dosya  (mcp-ci, mcp-smoke, signal-ci, repo-policy)
└── services/
    ├── btc-radar-mcp/   36 dosya  (btc_radar/, config/, docs/, scripts/, tests/, SPEC.md, CLAUDE.md)
    └── radar-signal/    80 dosya  (enricher/, scripts/, tests/, registry/, config/, docs/, user_data/strategies/)
```
(venv, `__pycache__`, ham veri hariç sayım)

### Birleşme nasıl yapıldı

| Soru | Cevap | Kanıt |
|---|---|---|
| Yöntem | `git subtree`, **`--squash` KULLANILMADAN** | ADR-0001 |
| Git geçmişi korundu mu | **EVET** | `516a998`, `aba25d1`, `97a88c0`, `ff113d8` hepsi erişilebilir |
| Alt dizin mi / submodule mü | **Alt dizin** (`services/…`); `.gitmodules` yok | dosya sistemi |
| Eski commit'ler duruyor mu | Evet, 32 eski + 4 monorepo commit'i | `git log` |
| İçe aktarma commit'leri | `ec4d304` (radar-signal), `80cadf7` (btc-radar-mcp) | git log |
| **ADR yazıldı mı** | **EVET — `docs/adr/0001-private-monorepo-birlesimi.md`.** EKSİK DEĞİL. | dosya mevcut |

ADR-0001 sonucu da dürüstçe kaydetmiş: eski commit'lerde dosyalar kaynak reponun kök yollarında görünür, `services/…` yolları yalnız import commit'inden sonra başlar; dosya bazlı `git blame` eski prefikse otomatik geçmez.

### Çakışmalar ve çözümü

| Dosya | Çakışma | Çözüm |
|---|---|---|
| `CLAUDE.md` | Her iki repoda vardı | Kök = 23 satırlık yönlendirici + platform kuralları; servis CLAUDE.md'leri (54 / 60 satır) olduğu gibi korundu. **Çakışma yok** |
| `config/`, `tests/`, lock dosyaları | — | Ayrı ağaçlarda kaldı, hiç birleştirilmedi (ADR-0001 kararı) |
| `Makefile`, `README.md` | Her iki repoda vardı | Kök seviyede yeni orkestrasyon dosyaları; servis kopyaları korundu |

### Birleşme sonrası ne çalışıyor

| Bileşen | Durum | Not |
|---|---|---|
| CI yolları | **ÇALIŞIR** | `signal-ci.yml` ve `mcp-ci.yml` `working-directory: services/…` ile güncellenmiş |
| btc-radar-mcp testleri | **ÇALIŞIR** | `uv run pytest` → 49 geçti (uv venv'i kendi kurar) |
| radar-signal testleri | **KISMİ** | Kod çalışıyor (116 geçti) ama **monorepoda `.venv` YOK**; testler ancak eski repodaki interpreter'a elle işaret edilerek koşturulabildi. Yerelde `pip install -r requirements.lock` gerekiyor |
| freqtrade `user_data/data` | **YOK** | Monorepoda yalnız `user_data/strategies/` var; ham veri `.gitignore`'da ve **fiziksel olarak yalnız eski `projeler/radar-signal` altında**. Monorepoda backtest koşulamaz |
| Veri manifesti | Var (`MANIFEST-20260803`) ama işaret ettiği dosyalar monorepoda yok | **borç** |

---

## 2. GIT DURUMU

| Alan | Değer |
|---|---|
| Dallar | `main` + `remotes/origin/main` (uzak tanımlı) |
| HEAD | `c32057f chore(monorepo): adapt services, provenance and CI` |
| Çalışma ağacı | **TEMİZ** (commit'lenmemiş/stash'li iş yok) |
| `feature/s-0002` | Monorepoda **YOK**. Dal tepesi düzleştirilerek `main`'e alındı |

**Son 5 commit (main):** `c32057f` monorepo uyarlama · `80cadf7` mcp geçmişi import · `ec4d304` signal geçmişi import · `cc568af` platform kökü · `7f8214a` private GitHub hazırlığı

**feature/s-0002 commit'lendi mi:** EVET — eski `projeler/radar-signal` reposunda `feature/s-0002` dalı hâlâ duruyor ve tepesi `6417cbe`. Bu tepe monorepo `main`'ine taşındı.

**.gitignore değerlendirmesi:** Kapsamlı ve doğru (secret, venv, ham veri, backtest artefaktı, sqlite, log). Eksik/fazla bir şey **tespit edilmedi**. `!**/.env.example` istisnası doğru kurulmuş.

**Eski repolar:** `projeler/radar-signal` ve `Desktop/btc-radar` hâlâ duruyor, venv ve veri onlarda. Arşiv/aktif ayrımı **tanımlanmamış** — borç.

---

## 3. TALİMAT TAKİBİ (ADIM 1/2/3)

| Madde | Durum | Kanıt |
|---|---|---|
| **ADIM 1** — çalışmayı commit'le | **YAPILDI** | `5fa5c50` (S-0002 + ADIM 1 hijyen) |
| ADIM 1 — registry verdict INVALID | **YAPILDI** | 7 S-0002 kaydı `INVALID — ölçüm hatası (bkz. …)` |
| ADIM 1 — registry `pairs` alanı | **KISMİ** | Alan `registrylib.py`'ye eklendi ve yeni kayıtlarda dolu (3/17). Eski 14 kayıt geriye doldurulmadı |
| ADIM 1 — S-0002 kartı güncelleme | **YAPILDI** | Kart durumu artık `GEÇERSİZ TEST (Ölçüm ve Kural Sapma Hatası)` |
| ADIM 1 — ADR-0004 üç düzeltme | **YAPILDI (fazlasıyla)** | 5 maddelik "Ek Kabul Kapıları": main koruması, kart↔kod uyumu, verdict kaydı, temiz ağaç, sermaye tükenmesi |
| ADIM 1 — ADR-0005 locked OOS | **YAPILDI** | `docs/adr/0005-locked-oos-sifirlama-ve-development-donemi.md` |
| **ADIM 2** — sizing düzeltmesi | **KISMİ** | S-0002b'de `custom_stake_amount` = cüzdanın %10'u. **`config.dryrun.json` hâlâ `stake_amount: 1000` sabit notional** — düzeltme platform geneli değil, tek strateji seviyesinde |
| ADIM 2 — sermaye tükenmesi kontrolü | **YAPILDI** | `scripts/measurement_validity.py::check_capital_depletion` + testleri (`debada7`) |
| ADIM 2 — beklenti metriği | **YAPILDI** | Aynı modülde expectancy (%/bps); S-0002b kartında kullanılmış |
| ADIM 2 — testler | **YAPILDI** | `tests/test_measurement_validity.py` (45 satır) |
| **ADIM 3** — S-0002b | **YAPILDI** | `8b35442` + `6417cbe`; strateji + kart + 3 koşu. Kart A'nın eksik 3 kuralı kodda: funding/premium filtresi (9 satır), saat-dilimi koşullaması (`groupby("hour")`), **sabit** ATR stop |

**S-0002b sonucu (geliştirme dönemi, BTC, 2024-01-01 → 2026-02-03):**

| Senaryo | İşlem | Beklenti/işlem | Net getiri | Kazanma |
|---|---|---|---|---|
| realistic | 3.967 | −17 bps | −47,06% | %30,9 |
| taker_heavy | 3.967 | −25 bps | −60,15% | %25,8 |
| stressed | 3.967 | −45 bps | −79,88% | %16,5 |

Üç senaryoda da **işlem sayısı aynı** → sermaye tükenmesi yok, ölçüm karşılaştırılabilir. Çıkışların %100'ü mum kapanışında yapısal/zaman çıkışı (S-0002'de %89 trailing stop idi). **Bu, S-0002'nin aksine Kart A'nın geçerli bir testidir ve ret gerekçesi meşrudur.**

---

## 4. CR TAKİBİ

### CR-001 — kart başlığında **UYGULANDI** (3 Ağu 2026)

| Madde | Durum | Kanıt |
|---|---|---|
| CR-1 DSR + çoklu maliyet | **KISMİ** | Kriterler SPEC §1.3'te (`159c86e`), `scripts/dsr.py` var; **hiçbir stratejide fiilen DSR hesaplanmadı** |
| CR-2 karartma modülü | **BEKLİYOR** | SPEC §2'de tanımlı (`3b67b7c`); `blackout/` modülü ve `config/blackout.yaml` **yok** |
| CR-3 backtest protokolü | **KISMİ** | Purged WF / embargo, A/B/C kıyası **kodda yok**; BTC/ETH ayrı kalibrasyon ve yayın-anı kuralı yalnız doküman |
| CR-4 strateji seti | **UYGULANDI** | SPEC §3.1 (`270233c`) |
| CR-5 costs.yaml | **UYGULANDI** | `config/costs.yaml` + `costslib.py` + testler |
| CR-6 look-ahead yasakları | **UYGULANDI** | CLAUDE.md kuralları + gate'ler |
| CR-7 quantstats | **BEKLİYOR** | Faz C/E raporlaması henüz yok |
| CR-8 rejim matrisi | **UYGULANDI** | SPEC §5.1 (`9155b32`) |

### CR-002 — P0 kısmen uygulandı

| Madde | Durum | Kanıt |
|---|---|---|
| **P0-1** snapshot + PIT depo | **UYGULANDI** | `97a88c0`; `core/store.py`, `core/snapshot.py`, ADR-0003; 100 replay bit-bit özdeş |
| **P0-2** Experiment Registry | **UYGULANDI (ama arızalı)** | Şema v2 tam; DSR↔registry testi geçiyor. **Ancak canlı registry dosyası okunamıyor — §6'ya bakınız** |
| **P0-3** Global/BTC/ETH rejim | **BEKLİYOR** | Plan bile çıkarılmadı; ETH varlık-rejimi kavramı kodda yok |
| **P0-4** state machine + outbox | **UYGULANDI** | `0a0b89a`, `dda7043`; 10dk kesinti kabul testi geçiyor |
| **P0-5** mum-içi simülatör | **UYGULANDI** | `4992345`; stop-önce kuralı + dinamik kayma + drift raporu |
| **P0-6** Signal Arbiter | **BEKLİYOR** | Kod yok. Artık 3 strateji dosyası var → çatışma politikası gerçek ihtiyaç hâline geldi |
| **P0-7** FOMC ayrımı + karartma | **KISMİ** | SPEC §3.1'de S-0004a/S-0005 ayrımı yapıldı; karartma modülü ve politika matrisi **kodda yok** |
| **P0-8** fail-closed | **UYGULANDI** | `enricher/policy.py` + `config/lifecycle.yaml` + testler |
| P1 (7 madde) | **BEKLİYOR** | P1-1 skor iyileştirmeleri, P1-3 locked-test disiplini (ADR-0005 kısmen karşıladı), diğerleri yok |
| P2 (9 madde) | **KISMİ** | P2-1/2/4/5/6/8 mesaj şablonlarında hazır; P2-3 Telegram butonları, P2-7 iptal bildirimi, P2-9 boyut satırı yok |

---

## 5. TEST VE KALİTE

| Ölçüm | radar-signal | btc-radar-mcp |
|---|---|---|
| pytest | **116 geçti**, 0 başarısız, 0 atlandı | **49 geçti**, 0 başarısız |
| ruff check | Temiz | Temiz |
| Coverage | **Yapılandırılmamış** — oran bilinmiyor | Yapılandırılmamış |

**Testi OLMAYAN modüller** (kanıt: `tests/` dizin listesi ↔ `scripts/`+`enricher/`):

| Modül | Test durumu |
|---|---|
| `enricher/telegram.py` | Test yok (ağ katmanı) |
| `enricher/fill.py` | Dolaylı (`test_app.py` üzerinden), doğrudan test yok |
| `scripts/pump.py`, `scripts/bt.py`, `scripts/data_manifest.py` | Test yok |
| `user_data/strategies/*.py` (3 strateji) | **Birim/sözleşme testi yok** — yalnız `test_card_code_alignment.py` metinsel uyum bakıyor |
| btc-radar `providers/` | Boş iskelet (Faz 1) |

**Anti-desen kapıları:**

| Strateji | lookahead-analysis | recursive-analysis | Kanıt |
|---|---|---|---|
| S-0001 | Koştu, `has_bias=No` (3 Ağu) | Koştu, ±0.000% | Kart belgeliyor |
| S-0002 | Koştu (3 Ağu) — **kart güncellenirken bu bölüm silinmiş** | Aynı | Eski kart / walkthrough |
| **S-0002b** | **Kartta hiç belgelenmemiş** | Kartta yok | **[?]** Koşulup koşulmadığı bilinmiyor; commit `8b35442` içeriğinde de kanıt yok |

S-0002b için DoD-4 (kabul kapısı çıktısının kartta olması) **karşılanmamış**.

---

## 6. DENEY VE HİPOTEZ DURUMU

### ⚠ KRİTİK ARIZA — registry dosyası okunamıyor

`registry/experiments.jsonl` **UTF-8 değil**: 17 satırın **8–14 arası 7 satırı** cp1252/cp1254 baytları içeriyor (ilk hatalı bayt `0x97`, pozisyon 4828). Sonuç:

- `registrylib.read_all()` → `UnicodeDecodeError` ile **çöküyor**
- Dolayısıyla `count_runs()`, `trials_for_dsr()`, `update_verdict()` **çalışmıyor** → DSR fiilen hesaplanamaz (CLAUDE.md kural 8, CR-002 P0-2)
- Testler bunu yakalamıyor çünkü hepsi `tmp_path` üzerinde sentetik dosya kullanıyor
- Bozukluk hem monorepoda hem eski repoda var → birleşmeden **önce** oluşmuş, birleşme taşımış
- **Sebebi bilinmiyor [?]**: `record_run`/`update_verdict` `encoding="utf-8"` kullanıyor; bozulmayı hangi yazıcının yaptığı tespit edilemedi

Aşağıdaki sayımlar dosyayı cp1252 ile elle çözerek çıkarıldı (üretim kodu bunu yapamaz):

| Ölçüm | Değer |
|---|---|
| Toplam kayıt | 17 |
| Hipoteze göre | S-0001: 7 · S-0002: 7 · S-0002b: 3 |
| Verdict | `INVALID`: 7 (S-0002) · `pending`: 4 · alan yok (şema v1): 6 |
| **Hâlâ `pending`** | **4 kayıt** — 1× S-0001 + **3× S-0002b** (kart "REDDEDİLDİ" diyor ama registry güncellenmemiş → ADR-0004 madde 3 ihlali) |
| `pairs` dolu | 3/17 (yalnız S-0002b) |
| `git_dirty: True` | 10/17 kayıt. S-0002b'nin 2/3 koşusu kirli ağaçtan, 1'i temiz |

### Hipotez kartları

| Kart | Durum | Not |
|---|---|---|
| S-0001 | **AKTİF — kontrol/taban** | Yayın adayı değil, tasarım gereği |
| S-0002 | **GEÇERSİZ TEST** | Ölçüm + kural sapması; registry INVALID |
| S-0002b | **REDDEDİLDİ (gerekçeli)** | Geçerli test; −17 bps beklenti. Kart↔registry verdict tutarsız |

Kart A dışındaki tüm kartlar (B–Q, 17 kart) `docs/research/hipotez-arastirmasi.md` içinde metin olarak duruyor; **`docs/hypotheses/` altına ayrı kart olarak işlenmedi** (CR-4 gereği) — borç.

### Test pencereleri

| Pencere | Durum |
|---|---|
| 2024-01-01 → 2026-02-03 | Geliştirme (kullanıldı: S-0001, S-0002, S-0002b) |
| **2026-02-03 → 2026-08-03** | **YANDI.** S-0002 ile locked OOS olarak açıldı, test geçersiz çıktı. ADR-0005 ile "Development Extension" olarak yeniden sınıflandırıldı |
| **2026-08-04 →** | **Tek temiz pencere.** İleri karantina; açılma koşulu: ≥4 hafta AND ≥100 sinyal AND ≥2 farklı rejim |

Bugün 4 Ağustos 2026 → temiz OOS penceresinde **henüz 0 gün** birikmiş durumda.

---

## 7. VERİ DURUMU

Konum: yalnız `C:/Users/TKA/projeler/radar-signal/user_data/data/binance/futures/` (monorepoda yok).

| Sembol | Zaman dilimi | Boyut | Aralık |
|---|---|---|---|
| BTC/USDT:USDT | 15m futures | 6,2 MB | 2019-09-08 → 2026-08-03 |
| BTC/USDT:USDT | **1m futures** | **85,2 MB** | aynı [?] tam aralık doğrulanmadı |
| BTC/USDT:USDT | 1h futures / mark / funding_rate | 1,6 / 1,8 / 0,08 MB | funding 2019-09-10'dan |
| ETH/USDT:USDT | 15m futures | 5,9 MB | 2019-11-27 → 2026-08-03 |
| ETH/USDT:USDT | **1m futures** | **81,3 MB** | aynı [?] |
| ETH/USDT:USDT | 1h futures / mark / funding_rate | 1,5 / 1,8 / 0,08 MB | — |

| Veri | Var mı |
|---|---|
| Futures OHLCV (15m/1h/1m) | **VAR** |
| Funding rate serisi | **VAR** (BTC + ETH, 1h) |
| Mark price | **VAR** |
| **Spot veri (BTC/USDT, ETH/USDT)** | **YOK** — hiç indirilmemiş |
| **Perp-spot premium bacağı** | **YOK** — spot veri olmadığı için hesaplanamaz. S-0002b'nin Kart A 4. koşulu bu bacak olmadan **eksik uygulanıyor [?]** (yalnız funding tarafı ölçülebiliyor) |
| Coinbase/Upbit/CoinGecko (btc-radar) | Provider'lar yazılmadı; veri toplanmıyor |

---

## 8. ÇELİŞKİ VE BORÇ LİSTESİ

### Çelişkiler

| # | Çelişki | Taraflar |
|---|---|---|
| Ç1 | Kart "REDDEDİLDİ" ↔ registry "pending" (S-0002b ×3) | ADR-0004 md.3 |
| Ç2 | ADR-0004 "main'e commit YASAK" ↔ S-0002/S-0002b işleri monorepo `main`'inde | ADR-0004 md.1 · git log |
| Ç3 | ADR-0004 "final koşular temiz ağaçta" ↔ S-0002b koşularının 2/3'ü `git_dirty: True` | ADR-0004 md.4 |
| Ç4 | CLAUDE.md kural 8 "registry'siz koşu geçersiz" ↔ registry dosyası okunamıyor | §6 arızası |
| Ç5 | Kart A "60 günlük dağılım" ↔ S-0002b `rolling(80)` = 20 gün (saat grubunda 4 bar/gün) | Kart A · kod |
| Ç6 | ADIM 2 sizing düzeltmesi strateji seviyesinde ↔ `config.dryrun.json` hâlâ sabit notional | S-0001/S-0002 hâlâ kırık sizing'de |
| Ç7 | Veri manifesti monorepoda ↔ işaret ettiği veri dosyaları monorepoda yok | §1 · §7 |
| Ç8 | CR-002 durum tablosu "3 Ağu" tarihli, S-0002b sonrası güncellenmemiş | CR-002 |

### Teknik borç

- Registry UTF-8 bozukluğu (en yüksek öncelik — kanıt zincirini fiilen kilitliyor)
- `radar-signal` monorepoda venv'siz; `user_data/data` yalnız eski repoda → monorepoda backtest koşulamaz
- Eski iki repo hâlâ duruyor, arşiv statüsü tanımlanmamış → çift doğruluk kaynağı riski
- 3 strateji için birim/sözleşme testi yok
- Coverage ölçümü hiç yapılandırılmamış
- `contracts/` boş — iki servis arasında sürümlü şema yok, entegrasyon başlamadı
- A–Q hipotez kartları ayrı dosyalara işlenmedi
- S-0002b için lookahead/recursive kanıtı belgesiz

### Bloke işler

| İş | Neden bloke |
|---|---|
| DSR hesabı (CR-1) | Registry okunamıyor |
| Kart A'nın 4. koşulunun tam uygulanması | Spot veri yok → premium bacağı hesaplanamaz |
| S-0003 rejim filtresi / Faz D entegrasyonu | btc-radar'da provider yok, HTTP transport yok, P0-3 planlanmadı |
| Yeni locked OOS koşusu | Karantina 2026-08-04'te başladı, koşullar (4 hafta / 100 sinyal / 2 rejim) dolmadı |
| Karartma modülü (CR-2, P0-7) | Ekonomik takvim + expiry veri kaynağı seçilmedi |

---

## 9. TEK PARAGRAF DÜRÜST ÖZET

Bugün itibarıyla sistem şunu **yapabiliyor**: iki servisi tek monorepoda geçmiş kaybetmeden barındırıyor (ADR'li, doğru yapılmış bir birleşme); 165 test yeşil ve lint temiz; sinyal yaşam döngüsü uçtan uca çalışıyor (state machine, outbox, fail-closed, kesinti dayanıklılığı testli); btc-radar tarafında point-in-time depo ve değişmez snapshot bit-bit deterministik; ve S-0002b ile ilk kez **metodolojik olarak geçerli** bir strateji testi üretildi — Kart A tam sadakatle uygulandı, sermaye tükenmesi olmadan ölçüldü ve −17 bps beklentiyle meşru biçimde reddedildi. Şunu **yapamıyor**: hiçbir strateji yayında değil ve yayına aday da yok; canlı sinyal hiç üretilmedi (Telegram token yok, dry-run daemon hiç çalışmadı); rejim beyni ile sinyal motoru arasında hiçbir bağlantı yok (contracts boş, P0-3 planlanmadı, provider'lar yazılmadı); Experiment Registry dosyası encoding bozukluğu yüzünden kendi kütüphanesiyle **okunamıyor**, bu yüzden DSR dahil çoklu-deneme düzeltmesi fiilen devre dışı; ve elde tek bir temiz OOS penceresi var, o da bugün başladı. Sıradaki tek mantıklı iş: **registry dosyasının encoding'ini onarmak ve bunu yakalayan bir regresyon testi eklemek** — çünkü kayıt okunamazken atılan her yeni backtest, kendi kurallarına göre geçersiz bir koşudur.
