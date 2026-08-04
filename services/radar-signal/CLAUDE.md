# CLAUDE.md — radar-signal Çalışma Kuralları

Bu dosya, bu repoda çalışan Claude Code oturumları için bağlayıcıdır. Her oturum başında sırayla oku: `SINYAL-SPEC.md` → `docs/change-requests/` (numara sırasıyla; CR'lar SPEC'i değiştirir) → son ADR'ler → `git log --oneline -10`.

## Proje kimliği
BTC ve ETH için intraday (15m/1h) sinyal + gerekçe üreten, freqtrade dry-run tabanlı, **asla emir göndermeyen** karar-destek sistemi. Kardeş servis: monorepodaki `services/btc-radar-mcp` (rejim beyni; HTTP ile entegre edilecek). Üç ilke: determinizm, test edilebilirlik, açıklanabilirlik. LLM'ler yalnız geliştirme zamanında; canlı döngüde asla.

## Teknoloji seti
- Python ≥3.11, freqtrade (güncel stable; futures modu, dry-run). Kurulum freqtrade'in resmî yöntemiyle (venv); ek araçlarımız için uv kullanılabilir.
- Test: pytest; lint: ruff (line-length 100). Commit öncesi lint+test zorunlu.
- Bildirim: freqtrade Telegram + webhook → `enricher/` (FastAPI mikroservis).
- Konfigürasyon: `config/costs.yaml` (CR-001/CR-5), `config/blackout.yaml`, strateji parametreleri stratejide değil config'de.

## Dizin yapısı
```
radar-signal/
  user_data/strategies/        # S-XXXX strateji sınıfları (tek üretim noktası)
  enricher/                    # webhook alıcısı: gerekçe + rejim satırı + state machine
  registry/                    # Experiment Registry (CR-002 P0-2)
  scripts/                     # walk-forward, veri indirme, replay, smoke
  config/                      # costs.yaml, blackout.yaml, freqtrade config'leri
  docs/
    hypotheses/                # H-kartları (kanıt düzeyi etiketli; ret kayıtları dahil)
    change-requests/           # CR-001, CR-002... (uygulanınca "UYGULANDI" işaretlenir)
    research/                  # hipotez araştırması, maliyet raporu, lookahead raporu
    reviews/                   # harici AI değerlendirme raporları (tarih klasörlü)
    adr/                       # NNNN-baslik.md
```

## Değiştirilemez kurallar
1. **Emir gönderen hiçbir kod yazılmaz.** Borsa API anahtarı yalnız public/read; config'de trade yetkili anahtar alanı boş kalır. Dry-run dışında mod açılmaz.
2. **`process_only_new_candles = True` tüm stratejilerde.** Kapanmamış mumla sinyal üretimi yasak.
3. **Global normalizasyon yasak:** DataFrame genelinde `.min()`/`.max()`/`MinMaxScaler().fit_transform` kullanılamaz; yalnız `rolling()` pencereli. (Belgelenmiş vaka ailesi: DevilStra/GodStraNew/Zeus/wtc.)
4. **Üst zaman dilimi** yalnız `merge_informative_pair` ile bağlanır; elle merge yazılmaz. `startup_candle_count` en uzun pencereye göre doğru set edilir.
5. **Türev/harici veri yayın-anı kuralı:** funding/OI/likidasyon/rejim verisi backtest'te yalnız `available_at ≤ karar_anı` ise kullanılabilir.
6. **Maliyetsiz backtest raporlanmaz.** Her koşu `config/costs.yaml` ile; sonuç raporunda maliyet senaryosu adı yazar. Backtest komutlarında `--timeframe-detail 1m` varsayılan; aynı detay mumunda stop+hedef çakışırsa stop önce sayılır (muhafazakâr kural).
7. **Out-of-sample kilidi:** locked-test dönemi hyperopt'a ve göz kararı iterasyona kapalıdır; bir kez açılır. Açıldıktan sonra strateji değişirse eski OOS sonucu "final" etiketi alamaz (CI kontrolü).
8. **Her deney Registry'ye yazılır** (başarısız/reddedilen dahil). Registry'siz backtest koşusu = geçersiz koşu. DSR'a giren N, registry'den gelir.
9. **Sinyal yaşam döngüsü yalnız state machine üzerinden** ilerler (CR-002 P0-4); durum atlaması veya elle durum yazımı yasak. Bildirimler outbox + `signal_id` idempotency ile.
10. **Yatırım tavsiyesi dili yasak.** "Al/sat/kesin" kalıpları hiçbir çıktıda yer almaz; "STOP ÇALIŞTI—kapandı" yerine "SİSTEM İNVALIDASYONU—gerçek pozisyonunuz otomatik kapatılmadı" dili (CR-002 P2-8). Her bildirimde invalidasyon + yasal not.
11. **Aynı anda yayında ≤3 strateji; araç/strateji eklemeden önce mevcut olana parametre eklemek değerlendirilir**, yeni strateji ADR ister.
12. Hipotez kartı olmayan strateji kodu yazılmaz; kart `docs/hypotheses/` altında ve kanıt düzeyi etiketli olmalı.
13. **Kanıt üreten iş `feature/` dalında yürütülür.** Strateji kodu, hipotez kartı, maliyet/boyutlandırma konfigürasyonu ve locked-OOS koşusu üreten her değişiklik `feature/<görev-adı>` dalında yapılır; bağımsız inceleme ve temiz ağaç (`git_dirty: False`) zorunludur (ADR-0004, ADR-0003). Altyapı/onarım/doküman işleri (test, CI, script, ADR, rapor) doğrudan `main`'e commit'lenebilir — bu işlerde "yazar ≠ incelemeci" korumasının koruyacağı bir ölçüm sonucu yoktur. Gerekçe ve geçmiş ihlallerin kaydı: `docs/CELISKI-DEFTERI.md` (Ç2).

## Test disiplini (Definition of Done)
İş şu dördü olmadan bitmedi sayılmaz: (1) birim/sözleşme testi yeşil, (2) ruff temiz, (3) davranış değişikliğinde SPEC/CR/ADR güncel, (4) strateji değişikliğinde freqtrade `lookahead-analysis` + `recursive-analysis` çıktısı temiz, kart-kod uyumu doğrulanmış ve hipotez kartına eklenmiş.
- Replay determinizm testi korunur: aynı veri + aynı commit → bit-bit aynı sinyal/skor/gerekçe.
- Canlı API'ye giden test yazılmaz; canlı kontrol yalnız `scripts/smoke` içindir.

## Oturum akışı
1. Büyük değişiklikte önce plan yaz, onay al, sonra uygula.
2. SPEC/CR'daki varsayım gerçekle çelişirse: dur, SPEC'i güncelle, ADR yaz, devam et. Sessiz uyarlama yasak.
3. Görev başına tek yazar; yazar ≠ incelemeci (ADR-0004). Başka araç/model çıktıları yalnız inceleme girdisidir; doğrudan merge edilmez.
4. CR uygulanınca dosyasının başına "DURUM: UYGULANDI (commit hash)" satırı eklenir.
