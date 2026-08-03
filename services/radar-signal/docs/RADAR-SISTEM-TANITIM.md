# RADAR SİSTEMİ — Bütünsel Ürün Tanımı (Harici Değerlendirme İçin)
**Sürüm:** 1.0 · **Tarih:** 3 Ağustos 2026 · **Sahip:** Eyüpcan (QA mühendisi / SDET)

> **Bu dokümanın amacı:** Aşağıda tanımlanan sistemin tamamını bağımsız bir yapay zekâ değerlendiricisine eksiksiz anlatmak. Değerlendiriciden beklenenler son bölümdedir. Doküman kendi kendine yeterlidir; ek bağlam gerektirmez.

---

## 1. Ürün Nedir? (Tek paragraf)

BTC ve ETH için **intraday (15 dakika ana / 1 saat teyit) al-sat sinyali üreten, her sinyali gerekçesi ve geçersizlik koşuluyla birlikte Telegram'a bildiren, pozisyonun yaşam döngüsünü (aç → izle → kapat) takip eden, ama asla emir göndermeyen** bir araştırma/karar-destek sistemidir. Sinyaller deterministik Python kodundan çıkar; LLM'ler canlı sinyal döngüsünde yer almaz. Sistem aynı monorepoda geliştirilen iki bağımsız çalışma zamanı bileşeninden oluşur: veri-ve-rejim beyni (**btc-radar**) ve sinyal motoru (**radar-signal**).

## 2. Temel Felsefe (üç ilke + üç ret)

**İlkeler:** (1) Determinizm — aynı veri her zaman aynı sinyali üretir. (2) Test edilebilirlik — backtest edilemeyen hiçbir fikir üretime giremez. (3) Açıklanabilirlik — her sinyal "neden" sorusuna cevap taşır.

**Retler:** (1) LLM canlı döngüde olmaz (nondeterministik, yavaş, açıklanamaz). (2) Emir gönderilmez, borsa hesabına yazma erişimi yoktur (dry-run/kağıt defter esastır). (3) "Kusursuz sinyal" vaadi yoktur — hedef, maliyet-sonrası istatistiksel avantaj + risk yönetimi + şeffaflıktır. Sistem yatırım tavsiyesi değildir; her bildirimde bu not ve invalidasyon koşulu yer alır.

## 3. Sistem Mimarisi (uçtan uca)

```
┌─────────────────────── VERİ KAYNAKLARI ───────────────────────┐
│ Binance USDT-M (mum, OI, funding, taker ratio) · Binance/     │
│ Coinbase/Upbit spot (premium hesabı) · Bybit (çapraz teyit)   │
│ bitcoin-data.com (STH-SOPR, CDD, netflow, likidasyon, kohort) │
│ CoinGecko [+CoinPaprika fallback] (dominance, breadth)        │
│ Alternative.me F&G · CBBI · Ekonomik/expiry takvimi           │
└──────────────┬──────────────────────────┬─────────────────────┘
               ▼                          ▼
   ┌── BTC-RADAR (FastMCP) ──┐   ┌── RADAR-SIGNAL (freqtrade) ──┐
   │ Provider ABC katmanı    │   │ 15m/1h mum verisi (ccxt)     │
   │ Normalizer → Validator  │   │ Deterministik stratejiler:   │
   │ Feature (percentile,    │   │  S-0001 kontrol (EMA+ATR)    │
   │  robust z-score)        │   │  S-0002 hacim-koşullu momentum│
   │ Scoring Engine:         │   │  S-0004 FOMC/seans kırılması │
   │  Yön (−100..+100)       │   │ Karartma modülü (FOMC/CPI/   │
   │  Kırılganlık (0..100)   │   │  expiry pencereleri)         │
   │  Güven (0..100)         │   │ Dry-run pozisyon defteri     │
   │  Rejim etiketi          │   │ İki hızlı çıkış:             │
   │ 8 MCP aracı (get_       │   │  · sinyal-çıkış: mum kapanışı│
   │  derivatives, onchain,  │   │  · stop/ROI: ~5 sn döngü     │
   │  premiums, scores...)   │   └──────────┬───────────────────┘
   └──────────┬──────────────┘              │
              │  HTTP (Faz D entegrasyonu)  │
              └────────────┬────────────────┘
                           ▼
              ┌── RATIONALE ENRICHER ──┐
              │ enter_tag → gerekçe    │
              │ + rejim skoru satırı   │
              │ + karartma durumu      │
              │ + invalidasyon seviyesi│
              └──────────┬─────────────┘
                         ▼
              TELEGRAM BİLDİRİMİ (insan okur, insan karar verir)
                         ▼
              KARAR GÜNLÜĞÜ + HAFTALIK SİNYAL KARNESİ
              (sistem defteri ve kullanıcı defteri ayrı izlenir)
```

### 3.1 Sinyal yaşam döngüsü
1. 15m mum kapanır → stratejiler koşar (kapanmamış mumla asla sinyal üretilmez; `process_only_new_candles=True`).
2. Tetiklenen sinyal sırayla iki kapıdan geçer: **karartma** (planlı olay penceresi mi?) ve **rejim** (btc-radar skoru: kırılganlık ≥60 ise uyarı/boyut kısma; güven <55 ise "veri yetersiz" damgası — fail-closed).
3. Geçen sinyal Telegram'a düşer: yön, strateji+etiket, gerekçe satırı, rejim satırı, referans giriş bölgesi, invalidasyon, yasal not.
4. Dry-run defteri pozisyonu hipotetik olarak açar ve **izler**: kural-tabanlı çıkış mum kapanışında, stop-loss/trailing/ROI hedefi ise ~5 saniyelik döngüde anlık fiyatla denetlenir ("fikrim değişti mum bekler, canım yanıyor beklemez").
5. Çıkış bildirimi (kâr/stop/zaman aşımı, hangisiyle kapandığı açık) Telegram'a düşer; sonuç karneye işlenir.

### 3.2 Rejim beyni (btc-radar) skorlaması
Metodoloji: her metrik yön katkısı d∈{−2..+2}, kırılganlık r∈{0,1,2} ve kalite/tazelik/bağımsızlık katsayıları (q,f,u∈[0,1]) üretir. Yön = 50·Σ(w·d·q·f·u)/Σ(w·q·f·u); benzer formülle kırılganlık; güven = kapsam×kalite. Ağırlıklar config'de (koda gömülü değil). Çift-sayım grupları tanımlı (ör. iki Fear&Greed sunumu tek oy). Rejim etiketleri: sağlıklı risk-on / kaldıraçlı coşku / sıkışmalı nötr / risk-off / deleveraging / birikim / veri yetersiz. Eksik veya bayat kaynak skoru şişirmez, güveni düşürür. Mimari borsa-mcp'den doğrulanmış desenlerle kuruldu: araç başına daraltılmış Literal şemalar, LLM'e "sonraki adım" tavsiyeli hata mesajları, kompakt markdown çıktı, kaynak bazlı TTL önbellek.

## 4. Bilimsel/İstatistiksel Disiplin (strateji fabrikası)

Ürünün asıl çekirdeği tek strateji değil, strateji üretme-eleme hattıdır:

1. **Hipotez kartı:** Her strateji, kanıt düzeyi etiketli (yüksek/orta/düşük) bir karttan doğar. Mevcut backlog, akademik literatür taramasından çıkan 17 karttır (momentum, jump-reversal, seans etkileri, funding/OI rejimleri, FOMC, volatilite kümelenmesi...). Araştırmanın ana bulgusu tasarımı doğrular: funding/OI/seans verileri yön sinyali değil **rejim filtresidir**; en kalıcı etkiler yön değil volatilite zamanlamasıdır.
2. **Backtest protokolü:** maliyet dahil (VIP0+BNB komisyon, çift-taraf slippage, tarihsel funding serisi); purged walk-forward (embargo boşluklu); son 6 ay hyperopt'a kapalı out-of-sample; BTC/ETH ayrı kalibrasyon, ETH ayrıca bağımsız doğrulama seti; ≥100 out-of-sample işlem; **Deflated Sharpe** ile çoklu-deneme düzeltmesi; 5 kademeli maliyet-stres matrisi (2→60 bps).
3. **A/B/C kıyası:** her strateji çıplak / +rejim / +rejim+karartma varyantlarıyla ölçülür; filtre iyileştirmiyorsa kullanılmaz — birleşim inanç değil ölçümdür.
4. **Look-ahead yasakları:** global min/max-MinMaxScaler normalizasyonu yasak (belgelenmiş gerçek vakalardan), üst zaman dilimi shift'li merge, türev verisi yalnız yayın anından itibaren kullanılabilir; freqtrade `lookahead-analysis` + `recursive-analysis` otomatik kabul kapısı; backtest `--timeframe-detail 1m` ile mum-içi stop/hedef simülasyonu.
5. **Karantina:** kabul edilen strateji ≥4 hafta dry-run'da izlenir; canlı-backtest sapması raporlanır; sapma anlamlıysa geri alınır. Reddedilen hipotezler de kayda geçer (yayın yanlılığına iç önlem). Aynı anda yayında ≤3 strateji.
6. **Stres/fuzz:** tarihsel veri yetmez; fat-tail sentetik veri (volatilite kümelenmeli üreteç) ile hiç yaşanmamış kriz senaryolarında davranış testi planlıdır.

## 5. Geliştirme Modeli (AI orkestrasyonu)

Tek yazar: Claude Code (tek monorepo, servis bazlı SPEC+CLAUDE.md anayasalarıyla; kural: spec'ten sapınca sessiz uyarlama yok, dur-güncelle-ADR). Çapraz inceleme: farklı model ailesi (Cursor/Codex) her strateji PR'ında özellikle look-ahead avı yapar (yazar ≠ incelemeci). Araştırma: ChatGPT deep research (hipotez backlog'u, maliyet parametreleri, ürün-API doğrulamaları), Gemini (büyük repo/CSV analizi). LLM'lerin tümü **tasarım-zamanı** araçlarıdır; çalışma zamanında yalnız deterministik kod + (sohbet üzerinden istenirse) btc-radar MCP'nin okunması vardır.

## 6. Mevcut Durum ve Yol

btc-radar: iskelet + 24 endpoint canlı doğrulaması tamam (23 OK; likidasyon için hazır seri bulundu, WS toplayıcı ihtiyacı düştü); 8 araçlı MVP inşası sürüyor. radar-signal: kurulum fazında; S-0001 kontrol backtest'i ilk kilometre taşı. Entegrasyon (rejim satırının sinyale girmesi) sonraki büyük adım; ardından 4 hafta karantına ve 3 aylık veriye dayalı değerlendirme. Otomasyon (emir) ancak bu verinin desteklemesi durumunda ve ayrı bir karar olarak tartışılır — bugünkü kapsamda yoktur.

## 7. Bilinen Sınırlar (kendi itiraflarımız)

- Sistemin izlediği pozisyon, kullanıcının gerçek pozisyonu değil sinyalin ideal kopyasıdır; insan gecikmesi/atlaması sapma yaratır (karar günlüğü bunu ölçer ama kapatmaz).
- Intraday'de maliyet küçük avantajları yer; bazı hipotez aileleri (jump-reversal, mum-sınırı) tam bu yüzden bilerek park edilmiştir.
- On-chain verinin bir kısmı ücretsiz ikame kaynaktan gelir (birincil ticari kaynak yerine); kalite katsayısı bunu yansıtır ama ölçüm inceliği kaybı vardır.
- Likidasyon "haritası" (tahmini kümeler) sistemde yoktur; yalnız gerçekleşen likidasyon kullanılır.
- Geçmişte belgelenmiş anomalilerin 2026'da aynı güçte sürdüğü varsayılmaz; her kart güncel out-of-sample ile yeniden ölçülür.

## 8. Değerlendiriciden İstenenler

Lütfen aşağıdaki sorulara, mümkünse madde numarası vererek cevap ver; genel övgü/eleştiri yerine spesifik ve gerekçeli itiraz tercih edilir:

1. **Mimari:** İki-proje ayrımı (veri/rejim beyni ↔ sinyal motoru) ve HTTP üzerinden entegrasyon tasarımında gördüğün zayıf nokta veya tekil hata noktası (SPOF) var mı?
2. **İstatistik:** Backtest protokolünde (Bölüm 4.2-4.4) hâlâ açık kalan bir sızıntı/önyargı kanalı görüyor musun? Deflated Sharpe + purged walk-forward + A/B/C kıyası kombinasyonunun gözden kaçırdığı bir şey?
3. **Sinyal yaşam döngüsü:** İki-hızlı çıkış modeli (mum kapanışı vs ~5 sn koruma döngüsü) ve `--timeframe-detail 1m` telafisi, canlı-backtest tutarlılığı için yeterli mi?
4. **Rejim skorlaması:** d·q·f·u ağırlıklı skor formülünün bilinen zayıflıkları (ör. katsayıların öznelliği, rejim geçişlerinde gecikme) için önerin ne olur?
5. **Ürün:** "Sinyal + gerekçe, emir yok" konumlanışında kullanıcı değeri açısından eksik gördüğün kritik bir özellik var mı (bizim listemizde olmayan)?
6. **Risk:** Bölüm 7'deki itiraf listesine eklenmesi gereken, bizim görmediğimiz bir sınır/risk?
7. **Kırmızı çizgi kontrolü:** Dokümanda determinizm/test edilebilirlik/açıklanabilirlik ilkeleriyle çelişen bir tasarım kararı tespit ediyor musun?

Cevaplarında önereceğin her değişiklik için lütfen belirt: hangi bileşeni etkiler, hangi mevcut ilkeyle uyumlu/çelişkili, ve doğrulanması için hangi test gerekir.
