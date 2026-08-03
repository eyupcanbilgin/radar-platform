# RESEARCH-RADAR.md — awesome-ai-in-finance Tam Triyaj
**Tarih:** 3 Ağustos 2026 · **Kaynak:** georgezouq/awesome-ai-in-finance README (398 satır, 234 girdi) · **Bağlam:** btc-radar-mcp + radar-signal projeleri

## Hüküm sözlüğü
- **KULLAN** — projeye somut girdi; ilgili faz belirtilmiş.
- **İZLE** — şimdi değil; belirli bir faz/koşul gelince yeniden bak.
- **İBRET** — bilinçli reddettiğimiz mimarinin örneği; ne yapmayacağımızı tanımlar.
- **ALAKASIZ** — hisse/Çin piyasası/DeFi-özel vb.; kapsamımız dışı.
- **ÖLÜ** — yıllardır bakımsız/terk edilmiş; teknoloji eskimiş.

---

## Bölüm bölüm hüküm

### Agents (15 girdi)
Toplu hüküm: **İBRET** (ATLAS, OpenFinClaw, Vibe-Trading, Cod3x, AgentFund, ProfitPlay, oracle3 vb.) — LLM'i canlı karar döngüsüne koyan, determinizm ve backtest edilebilirlikten feragat eden mimariler. Bizim üç ilkemizin (determinizm, test edilebilirlik, açıklanabilirlik) anti-örneği.
İstisnalar: **TradingAgents, FinRobot → İZLE** (Faz E sonrası; çoklu-ajan *analiz* orkestrasyonu fikri, işlem döngüsü değil). **TraceArena → İZLE** (denetlenebilir ajan değerlendirme fikri ilginç; kanıt-bağlantılı aksiyon kaydı bizim gerekçe mekanizmamızla akraba).

### LLMs (17 girdi)
Toplu hüküm: **ALAKASIZ/İZLE** — FinGPT/FinBERT fine-tune dünyası bizim ürünün dışında; haber duyarlılığı Faz D+ olursa FinBERT yerine güncel genel modeller kullanılır.
İstisna: **Financial Statement Analysis with LLMs (SSRN) → İZLE** (LLM'in *analiz* gücünün kanıtı; canlı sinyal için değil). "ChatGPT'ye indikatör sordum" türü girdiler (TradeSmart, OctoBot blog) → **İBRET**: indikatör seçimini popülerlik anketiyle yapmak, hipotez disiplinimizin tersi.

### Skills (4 girdi)
- **Trading Ledger → KULLAN (Faz C):** karar günlüğü / sinyal karnesi tasarımına temel. Tez+plan+duygu kaydı, haftalık karar-notlama.
- **CFA Bias Detection → KULLAN (Faz B/E):** hipotez kartı ve değerlendirme raporu incelemesine önyargı kontrol listesi olarak uyarlanır.
- XVARY (SEC/hisse), Ethical Capital → **ALAKASIZ**.

### MCP Servers — Market Data (12 girdi)
- **Sharpe (sharpe.ai) → KULLAN-ADAY (btc-radar Faz 2/D):** funding/türev/haber tek kaynak; ücretsiz katman doğrulanacak (fizibilite kuyruğuna eklendi).
- **CoinPaprika → KULLAN (btc-radar, düşük maliyet):** CoinGecko fallback provider'ı; anahtarsız.
- **DexPaprika, evm-mcp, Philidor → ALAKASIZ** (DeFi/zincir-içi operasyon).
- **tradingview-mcp → İZLE (oyuncak):** sohbette görsel/screener keyfi için; sinyal hattına giremez (gayriresmî, backtest edilemez).
- **crypto-indicators-mcp → ALAKASIZ:** indikatörleri freqtrade zaten hesaplıyor; MCP'den indikatör çekmek mimariyi bulandırır.
- FRED → **İZLE** (makro karartma takvimi Faz B'de gerekirse ABD verisi için).
- edgartools, financial-datasets, FinanceMCP, akshare, alphavantage, FMP, yahoo, massive → **ALAKASIZ** (hisse/SEC/Çin odaklı).

### MCP Servers — Trading Execution (8 girdi)
Toplu hüküm: **ALAKASIZ + İLKE GEREĞİ RET** — emir gönderen MCP'ler (Alpaca, OKX agent-trade-kit, Kraken CLI, MetaTrader, IB, Trade It). Ürün tanımımız "emir yok"; bu bölüm bizim için kapalı kapı. (İleride otomasyon tartışılırsa bile emir katmanı MCP/LLM üzerinden DEĞİL, deterministik servisle olur.)
İstisna: **QuantConnect MCP → İZLE** (bulut backtest'i LLM'den yönetme deneyi; freqtrade yerelimiz varken gerek yok).

### MCP Servers — Research & Analysis (4 girdi)
- **tradememory-protocol, Hindsight → İZLE (Faz E+):** strateji-evrimi hafızası fikri; şimdilik hipotez kartları + git bizim hafızamız.
- maverick-mcp, sec-edgar-mcp → **ALAKASIZ**.

### Papers (12 girdi)
- **Sornette — Dragon-Kings → KULLAN:** kırılganlık skorunun teorik dayanağı; metodoloji dokümanına referans.
- Bachelier 1900, Osborne 1959 → **İZLE (kültür):** rastgele yürüyüş temeli; "kusursuz sinyal yoktur" cümlemizin ataları.
- RL makaleleri (1994–2020, FinRL, Ensemble) → **İBRET/ALAKASIZ:** bilinçli girmediğimiz yol; gerekçe SINYAL-SPEC §5.
- Ten Financial Applications of ML → **İZLE** (genel kültür).

### Courses & Books & Blogs (14 girdi)
- **Advances in Financial Machine Learning (López de Prado) → KULLAN (protokolün omurgası):** purged walk-forward, deflated Sharpe, meta-labeling → SINYAL-SPEC §3'e işlenecek. **Advanced-Deep-Trading** reposu kod referansı.
- **QuantResearch (letianzj) → KULLAN (hipotez kaynağı):** backtest'li strateji arşivi; ChatGPT hipotez araştırmasına ek girdi.
- Udacity/NYU/Coursera kursları → **İZLE (kişisel eğitim):** proje bağımlılığı değil.
- Manning kitapları, KeepRule, CFTE → **İZLE/ALAKASIZ**.
- Hands-on train-deploy-ML (Paulescu) → **İZLE:** MLOps hijyeni; ML katmanı açılırsa (Faz E+) döneriz.

### Strategies & Research — Time Series / Portfolio / HFT / Event / Crypto (35+ girdi)
- RL/DQN/LSTM strateji repoları (Personae, FinRL, tforce_btc_trader, LSTM-Crypto, NeuroEvolution, gekko-ANN…) → **İBRET/ÖLÜ:** 2017-2020 dalgası; determinizm-testedilebilirlik ilkelerimizi ihlal.
- **DeepAlpha → İZLE (Faz E+ tek modern istisna):** walk-forward doğrulamalı ensemble; ML günü gelirse ilk referans.
- HFT bölümü → **ALAKASIZ:** tick/orderbook HFT bizim 15m ürünümüzün başka bir spor dalı.
- trump2cash → **İZLE (eğlencelik):** olay-güdümlü sinyalin uç örneği; karartma mantığımızın ters aynası.
- stockpredictionai → **İBRET:** etkileyici görselli, doğrulanması zor "komple süreç" anlatısı.

### Technical Analysis (17 girdi)
- Gekko ekosistemi (7 girdi) → **ÖLÜ:** Gekko yıllardır bakımsız.
- crypto-signal → **ÖLÜ/İZLE:** eski nesil sinyal botu; sadece "bildirim şablonu nasıl kurgulanmış" diye bakılabilir.
- **Wickra → İZLE:** 500+ indikatörlü modern Rust çekirdek; freqtrade'in TA seti yetmezse alternatif.
- finta, pandas_talib → **İZLE:** indikatör formül referansı.
- QTradeX, quant-trading → **İZLE** (hipotez fikir havuzu).
- Chartscout, MarginSafe → **ALAKASIZ** (kapalı ürünler).

### Data Sources — Crypto (12 girdi)
- **CoinPaprika → KULLAN** (yukarıda). **Sharpe → KULLAN-ADAY** (yukarıda).
- **PreReason → İZLE (rakip/kıyas):** "AI-hazır rejim brifingleri" satıyor — bizim compute_scores'un ticari benzeri. Faz E'de çıktı kalitesi kıyaslaması için değerli.
- **Satoshi API → İZLE:** ücret/mempool istihbaratı; on-chain katmanına niş ek olabilir.
- CryptoInscriber, Gekko-Datasets → **ÖLÜ**. BitBank.nz ("AI tahmin API'si") → **İBRET**. CoinPulse, Frostbyte → **ALAKASIZ/İZLE** (fiyat verimiz zaten var). DexPaprika, TBD Predict → **ALAKASIZ**.

### Data — News / Alternative / Prediction Markets (6 girdi)
- WorldMonitor → **İZLE (Faz D):** haber/jeopolitik izleme; karartma+acil fren tasarımında fikir.
- Adanos sentiment → **İZLE (Faz D+):** X/Reddit duyarlılığı; Grok planımızla çakışır, kıyaslanır.
- Pizzint (Pentagon pizza endeksi) → **ALAKASIZ (eğlencelik).**
- Parsec/PolyMind (tahmin piyasaları) → **İZLE:** tahmin piyasası fiyatları makro olay olasılığı için ilginç sinyal; Faz D+ hipotez adayı ("FOMC sürpriz olasılığı karartma penceresini genişletsin mi?").

### Research Tools (18 girdi)
- **pyfolio + empyrical → KULLAN (Faz E):** risk/performans metrikleri; değerlendirme raporunu derinleştirir. alphalens → İZLE (faktör analizi; ML gününe).
- **CRNG → KULLAN (Faz C+):** fat-tail sentetik veri ile stres/fuzz testi.
- **Chart Library → İZLE (merak):** benzer grafik deseni arama; hipotez keşfinde eğlenceli olabilir, kanıt değeri düşük.
- TensorTrade, JAQS, zvt, btgym → **ALAKASIZ/ÖLÜ** (RL/Çin odaklı). WFGY → İZLE (LLM ajan stres testi; radar skill'ini test ederken bakılabilir). NeuPortal → İZLE (tahmin-hesap-verebilirlik fikri güzel: kilitli, zaman damgalı tahmin — bizim dry-run defterimiz zaten bunu yapıyor). Diğerleri (Synthical, DDScore, FN2, QuantLink, Coinugget, WalletLens, CongressionalStockBrain) → **ALAKASIZ**.

### Trading System (16 girdi)
- **OpenBB → İZLE (Faz E):** açık kaynak araştırma terminali; raporlama/görselleştirme tarafında işbirliği potansiyeli.
- zipline/backtrader/rqalpha/lean/kungfu/the0/finclaw → **ALAKASIZ:** motor kararımız freqtrade; ikinci motor taşımayız (tek-motor ilkesi).
- Kripto botları (zenbot, bot18, magic8bot, catalyst, abu, MACD) → **ÖLÜ.**

### TA Lib / Exchange API / Framework / Visualizing / GYM (15 girdi)
- finta, tulipnode, techan.js → **İZLE** (formül/görselleştirme referansı). **KLineChart → İZLE (Faz E):** dashboard yaparsak hafif mum grafiği kütüphanesi — dopamine-site frontend deneyiminle birleşebilir.
- Exchange API bölümü → **ALAKASIZ/İLKE GEREĞİ RET** (emir katmanı). PENDAX → ÖLÜ (FTX!).
- GYM ortamları → **İBRET/ALAKASIZ** (RL). TraderHarness → **İZLE:** "kontaminasyon-dirençli backtest" kavramı (point-in-time maskeleme) bizim look-ahead avımızın akademik akrabası; fikir olarak değerli.

### Others (10 girdi)
- Hindsight → yukarıda İZLE. Registry Broker, AgentMarket, MeterCall, LendTrain, Floom → **ALAKASIZ.**
- Stock-Prediction-Models, Financial ML, awesome-quant vb. alt listeler → **İZLE (ikinci halka):** ihtiyaç doğunca konuya özel dalınır; "listenin listesi"ni komple okumak aynı tuzağın büyüğü.

---

## Net sonuç
| Hüküm | ~Adet | Anlamı |
|---|---|---|
| KULLAN | 10 | López de Prado, Sornette, Trading Ledger, CFA bias, CoinPaprika, Sharpe(aday), CRNG, pyfolio+empyrical, QuantResearch, Advanced-Deep-Trading |
| İZLE | ~35 | Fazı/koşulu tanımlı bekleme listesi (bu doküman) |
| İBRET | ~25 | LLM-döngüde / RL / anket-indikatör mimarileri — ret gerekçeli |
| ALAKASIZ | ~110 | Hisse, Çin, DeFi, emir-katmanı, kapalı ürünler |
| ÖLÜ | ~25 | Gekko/zenbot çağı |

**"Bizden önde olan var mı?" sorusunun cevabı:** Parça parça evet — PreReason rejim brifingi satıyor, Sharpe türev verisi topluyor, Coinugget RSI sinyali gösteriyor. Ama hiçbiri şunların **birleşimini** yapmıyor: senin metodolojin (yön/kırılganlık/güven + fail-closed) + disiplinli strateji fabrikası (hipotez kartı, deflated Sharpe, ret kayıtları) + tam şeffaf gerekçeli sinyal. Rakipler ya veri satıcısı (kullanırız) ya kara-kutu ajan (reddederiz). Önde olunacak yer orası değil, bizim kurduğumuz kesişim.

**Bakım kuralı:** Bu liste yaşayan bir pano; ayda bir `git pull` + fark taraması yapılır, yeni girdiler bu dokümana hükümle eklenir. "Hepsini incele" bir kere yapılan iş değil, hafif ve sürekli bir radar taramasıdır.

---

# v1.1 EK — Aşama 2 Sağlık Taraması (3 Ağustos 2026)

Triyajı geçen 30 GitHub adayına canlılık taraması yapıldı (son commit tarihi, atom feed üzerinden). Sonuç: 20 CANLI (2025+), 2 DURGUN (2023-24), 8 ÖLÜ (≤2022).

## Hüküm değişiklikleri (tarama sonucu)
| Girdi | Eski hüküm | Yeni hüküm | Gerekçe |
|---|---|---|---|
| pyfolio, empyrical, alphalens | KULLAN/İZLE | **ÖLÜ → yerine quantstats** | Üçü de 2020'de durmuş (Quantopian kapandı). Aynı işi yapan bakımlı alternatif: `quantstats` — freqtrade ile hazır entegrasyonu var. Faz E raporlaması quantstats ile yapılır. |
| finta, pandas_talib | İZLE | **ÖLÜ** | 2022/2018'de durmuş. İndikatör referansı olarak `pandas-ta` + freqtrade dahili seti kullanılır. |
| Advanced-Deep-Trading (repo) | KULLAN | **İZLE (arşiv referansı)** | Repo 2020'de durmuş; **kitap (López de Prado) KULLAN olarak kalır** — metodoloji eskimez, kod örneği eskir. |
| QuantResearch (letianzj) | KULLAN | **KULLAN (notlu)** | 2023'te durgunlaşmış ama backtest arşivi okuma malzemesi olarak hâlâ değerli; kod bağımlılığı alınmaz. |
| crypto-signal | ÖLÜ/İZLE | **ÖLÜ (kesinleşti)** | 2022. Bildirim şablonu için bile bakmaya değmez. |
| trump2cash | İZLE (eğlencelik) | **ÖLÜ** | 2022. |

## Canlılığı doğrulananlar (hüküm aynen kalır)
freqtrade (bugün push almış — motor kararı sağlam), trading-ledger, CFA-skills, CRNG, DeepAlpha, wickra, tradingview-mcp, tradememory-protocol, OpenBB, KLineChart, TraderHarness, worldmonitor, Satoshi API, QTradeX, WFGY, fred-mcp-server, TradingAgents, FinRobot, TraceArena (son üçü İBRET/İZLE sınıfında kalır — canlı olmaları mimari itirazımızı değiştirmez).

## Güncel KULLAN listesi (v1.1)
López de Prado kitabı · Sornette makalesi · Trading Ledger · CFA bias-detection · CoinPaprika · Sharpe (doğrulama kuyruğunda) · CRNG · **quantstats** (pyfolio yerine) · QuantResearch (okuma).

## Aşama 3 iş bölümü (derin inceleme kuyruğu)
| İnceleme | Kim | Ne sorulacak |
|---|---|---|
| Sharpe, PreReason, Parsec, Adanos (ürün/site) | ChatGPT deep research | Ücretsiz katman gerçek mi; API sözleşmesi, limitler, veri tanımları; kayıt şartları |
| trading-ledger + CFA-skills (skill uyarlama) | Claude (bu sohbet) | Faz C karar günlüğü tasarımına uyarlama — sırası gelince |
| CRNG | Claude Code | Faz C+ stres testi entegrasyonu öncesi kod okuması |
| tradingview-mcp | Eyüpcan (keyfî) | Oyuncak olarak kurulum; sinyal hattına girmez |
