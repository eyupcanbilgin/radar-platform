# Radar Signal (`radar-signal`)

**BTC & ETH Intraday Sinyal ve Karar-Destek Servisi**

`radar-signal`, Bitcoin (BTCUSDT) ve Ethereum (ETHUSDT) vadeli işlem piyasaları (USDT-M Perpetual) için 15 dakikalık (15m) ve 1 saatlik (1h) grafiklerde deterministik al/sat yönlü kurulup sinyalleri ve gerekçeleri üreten, `freqtrade` tabanlı bir karar-destek ve strateji doğrulama sistemidir.

> [!IMPORTANT]
> **Yasal ve Etik Çerçeve:** Bu sistem **kesinlikle emir göndermez**, borsa hesaplarına yazma yetkisiyle bağlanmaz ve yatırım tavsiyesi niteliğinde değildir. Çıktısı *"koşullu sinyal + gerekçe + invalidasyon (stop)"* bilgisidir. İşlem kararı ve sorumluluğu tamamen kullanıcıya aittir.

---

## 🚀 Öne Çıkan İlkeler ve Kurallar

1. **Sadece Karar Destek (Emir Yok):** Borsa API anahtarları yalnızca okuma (read/public) yetkilidir. Config dosyalarında trade yetkili anahtar alanları boş bırakılır. Dry-run modu haricinde mod açılmaz.
2. **Deterministik Kod (Canlı Döngüde LLM Yok):** Canlı sinyal üretiminde hiçbir AI/LLM çağrısı yapılmaz. Tüm sinyaller deterministik Python strateji sınıflarıyla üretilir.
3. **Maliyetli Backtest Zorunluluğu:** Maliyetsiz backtest raporlanmaz. Komisyon, tek yön kayma (slippage) ve tarihsel fonlama (funding) oranları `config/costs.yaml` üzerinden zorunlu olarak uygulanır.
4. **Anti-Desen ve Look-Ahead bias Yasakları:** Kapanmamış mumla sinyal üretimi (`process_only_new_candles = True`) ve DataFrame genelinde global normalizasyon (`.min()`, `.max()`, `fit_transform()`) kesinlikle yasaktır. Sadece geçmişe dönük `rolling()` pencereleri kullanılır.
5. **Görev Başına Tek Yazar ve Bağımsız İnceleme (ADR-0004):** Kod geliştirmesini yapan oturum/geliştirici kendi kodunun nihai denetçisi olamaz. Tüm PR'lar kabul kapılarından (`lookahead-analysis`, `recursive-analysis`, `pytest`, `ruff`) geçmek zorundadır.

---

## 🛠️ Kurulum ve Başlangıç

### 1. Monorepoyu Klonlama ve Sanal Ortam Oluşturma
```bash
git clone git@github.com:KULLANICI_ADI/radar-platform.git
cd radar-platform/services/radar-signal

# Python sanal ortamı oluşturma (Python >= 3.11)
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate
```

### 2. Bağımlılıkları Yükleme
```bash
pip install -r requirements.lock
```

### 3. Çevre Değişkenleri (`.env`)
Örnek `.env.example` dosyasını `.env` adıyla kopyalayın:
```bash
cp .env.example .env
```
Telegram bildirimleri için `RADAR_SIGNAL_DELIVERY_MODE=telegram` seçin ve
`TELEGRAM_BOT_TOKEN` ile `TELEGRAM_CHAT_ID` değerlerini doldurun. Yalnız yerel geliştirmede
`RADAR_SIGNAL_DELIVERY_MODE=console` kullanılabilir; eksik Telegram secret'ı otomatik olarak
console'a düşmez.

Enricher webhook mutasyonları için ayrıca `RADAR_SIGNAL_WEBHOOK_SECRET` gerekir. İstemci ham
JSON gövdesini `timestamp.nonce.body` HMAC-SHA256 sözleşmesiyle imzalamalıdır; ayrıntılar
Signal ADR-0015'tedir. Freqtrade'in yerleşik webhook'u dinamik imza üretmediği için signer
adaptörü olmadan doğrudan enricher'a bağlanmaz.

---

## BTCUSDT 1h Paper Karar Runtime'ı

İlk dar ürün dilimi public Binance USD-M kapanmış mumlarıyla tek-sefer çalıştırılabilir:

```powershell
.venv\Scripts\python.exe scripts\run_hourly_decision.py
```

Sürekli UTC scheduler modu açıkça seçilir:

```powershell
.venv\Scripts\python.exe scripts\run_hourly_decision.py --daemon
```

Runtime emir göndermez ve API anahtarı kullanmaz. MCP artık gerçek Binance türev gözlemlerinden
fail-closed exact-hour context yayınlayabilir; ancak skorlama kuralları ve kabul edilmiş yönsel
setup henüz olmadığı için bugünkü dürüst çıktı yine `WAIT`tir. Producer şu an ayrı one-shot
CLI'dır, scheduler/supervision değildir. Exact-hour inbox, retry/grace, replay ayrımı ve
işletim sınırları için `decision_engine/README.md` dosyasına bakın.

---

## 🧪 Testler ve Doğrulama

### Birim Testlerini Çalıştırma (pytest)
```bash
python -m pytest
```

### Kod Biçimlendirme ve Linting (ruff)
```bash
.venv\Scripts\ruff check .
```

### Anti-Lookahead ve Recursive Bias Testleri
Yeni bir strateji PR'ı açılmadan önce aşağıdaki kabul kapıları çalıştırılmalıdır:
```bash
# Look-ahead Bias Testi
.venv\Scripts\freqtrade lookahead-analysis --strategy S0001EmaCross --timerange 20250101-20250401 -c config/config.dryrun.json

# Recursive Indicator Testi
.venv\Scripts\freqtrade recursive-analysis --strategy S0001EmaCross --timerange 20250101-20250201 -c config/config.dryrun.json
```

---

## 📈 Backtest ve Deney Kaydı (Experiment Registry)

Tüm backtest koşuları `scripts/bt.py` sarmalayıcısı üzerinden yürütülür ve sonuçlar `registry/experiments.jsonl` dosyasına kaydolur:

```bash
# S-0001 Kontrol Stratejisini Gerçekçi (realistic) maliyetle backtest etme:
python scripts/bt.py --strategy S0001EmaCross --hypothesis S-0001 --scenario realistic --timerange 20240101-20260203

# Taker heavy maliyet senaryosuyla çalıştırma:
python scripts/bt.py --strategy S0001EmaCross --hypothesis S-0001 --scenario taker_heavy --timerange 20240101-20260203
```

---

## 📂 Proje Dizin Yapısı

```text
radar-signal/
  ├── decision_engine/        # BTC 1h feature/karar/ledger/runtime çekirdeği
  ├── user_data/strategies/   # S-XXXX Strateji sınıfları ve konfigürasyonları
  ├── enricher/               # Webhook alıcısı: gerekçe + rejim satırı + state machine (FastAPI)
  ├── registry/               # Experiment Registry (experiments.jsonl)
  ├── scripts/                # bt.py, maliyet çözücüleri, manifest ve araçlar
  ├── config/                 # costs.yaml, blackout.yaml, config.dryrun.json
  ├── docs/                   # Şartnameler, CR'lar, ADR'ler ve hipotez kartları
  └── tests/                  # Pytest birim ve entegrasyon testleri
```

---

## 🤝 Takım Çalışması ve Git Akışı (Workflow)

- **`main` dalına doğrudan commit atılması YASAKTIR (Kural 13).**
- Yeni bir iş veya strateji üzerinde çalışırken dal açın: `git checkout -b feature/<görev-adı>`
- Değişikliklerinizi commit etmeden önce `pytest` ve `ruff check .` çalıştırarak yeşil olduğundan emin olun.
- Ortak çalışmada her deney `registry/experiments.jsonl` dosyasında izlenir; silinmez veya geçmiş kayıtlar değiştirilmez.
