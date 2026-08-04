# btc-radar-mcp

Bitcoin merkezli kripto piyasa analizi için **salt-okunur** FastMCP sunucusu. Emir göndermez,
borsa hesabına bağlanmaz, yatırım tavsiyesi üretmez. Skorlama deterministiktir; yorum LLM'e aittir.

Ayrıntılar: [SPEC.md](SPEC.md) (işlevsel şartname) ve [CLAUDE.md](CLAUDE.md) (çalışma kuralları).

## Kurulum ve çalıştırma

```bash
uv sync            # bağımlılıklar + venv
uv run btc-radar   # stdio üzerinde MCP sunucusu
```

MCP'de bugün çalışan piyasa aracı:

```text
get_derivatives(metric="all")
```

Bu araç Binance public BTCUSDT USD-M `mark_price`, `funding_rate` ve `open_interest`
gözlemlerini döndürür. Henüz yön/rejim skoru üretmez; yanıtta
`scoring_blocker=signal_rules_unavailable` görünür.

Claude Desktop yapılandırması:

```json
{
  "mcpServers": {
    "btc-radar": {
      "command": "uvx",
      "args": [
        "--from",
        "C:/ABSOLUTE/PATH/radar-platform/services/btc-radar-mcp",
        "btc-radar"
      ]
    }
  }
}
```

`--from` değeri makinenizdeki monorepo konumuna giden mutlak yol olmalıdır.

## Geliştirme

```bash
uv run pytest                                  # testler
uv run ruff check --fix && uv run ruff format  # lint + format
uv run python scripts/verify_endpoints.py      # canlı endpoint doğrulaması (smoke)
```

Smoke raporu üç durumu ayırır: `OK`, `FAIL` (zorunlu sözleşme kırılması, çıkış kodu 1) ve
`blocked_in_environment` — uç, isteğin geldiği ülke/ağ yüzünden reddetti; sözleşme ne
doğrulandı ne de ihlal edildi, çıkış kodu bozulmaz. GitHub-hosted runner'da Binance uçları
bu durumdadır, dolayısıyla **günlük CI koşusu Binance zinciri için kanıt üretmez**; kanıt
engellenmemiş bir ağdan üretilir. `--fail-on-blocked` engeli de başarısızlık sayar (çıkış
kodu 2) — engellenmemiş bir ağdan koşarken kullanın. Gerekçe:
[ADR-0007](docs/adr/0007-cografi-engel-siniflandirmasi.md).

## PIT toplama ve signal context yayını

Toplama ile yayın bilinçli olarak ayrıdır: kapanıştan sonra çekilen değer geçmiş saate
backdate edilmez.

```bash
# Bir kereye mahsus geçmiş: settled funding + saatlik OI + spot 1h OHLCV (API key yok)
uv run btc-radar-producer backfill \
  --pit-db ./var/pit.sqlite --funding-days 120 --open-interest-days 30 --spot-days 120

# Saat boyunca düzenli çalıştırılacak public collector; en yeni geçmiş sayfasını da yazar
uv run btc-radar-producer collect --pit-db ./var/pit.sqlite

# Kapanmış tam UTC saat için immutable context yayınla
uv run btc-radar-producer publish \
  --as-of 2026-08-04T12:00:00Z \
  --pit-db ./var/pit.sqlite \
  --snapshot-db ./var/snapshots.sqlite \
  --context-root ../radar-signal/var/decision-context
```

`collect` komutunun geçmiş sayfasını da yazması gereklidir: Binance saatlik OI geçmişini
yalnız ~30 gün saklar, ondan eskisi ancak kendi PIT depomuzda bulunabilir.

Spot OHLCV backfill edilebilir; basis ve order-book uçları yalnız güncel snapshot verir.
Bu yüzden basis/depth geçmişi OHLCV'den tahmin edilmez: `status` bunları `live_only` olarak
raporlar ve yalnız collector çalışırken biriken gerçek satırları ölçer (ADR-0008).

## Sürekli çalıştırma ve işletim kanıtı (ADR-0006)

`run` iki ritmi tek döngüde yürütür: saat içinde toplama, saat kapanınca yayın.

```bash
# Tek geçiş — Windows Task Scheduler / cron için önerilen biçim
uv run btc-radar-producer run \
  --pit-db ./var/pit.sqlite --snapshot-db ./var/snapshots.sqlite \
  --heartbeat-db ./var/heartbeat.sqlite \
  --context-root ../radar-signal/var/decision-context

# Servis yöneticisi olan ortamlarda sürekli mod
uv run btc-radar-producer run --daemon --lock-file ./var/producer.lock ...

# İşletim kanıtı: koşu kütüğü + toplanan serinin kapsaması
uv run btc-radar-producer status --window-days 7
```

**Windows'ta süpervizör olarak Task Scheduler önerilir:** görevi her dakika `run` (tek geçiş)
çalıştıracak şekilde tanımlayın. Çöken bir süreç bir sonraki dakikada kendiliğinden geri
gelir; daemon modunda bunu yapan bir dış süpervizöre ihtiyaç duyarsınız.

`status` iki ayrı soruyu ayrı ayrı yanıtlar ve ikisi birlikte "kesintisiz çalıştı" iddiasının
kanıtıdır:

- `tasks` — süreç gerçekten koştu mu, en son ne zaman başarılı oldu, üst üste kaç hata var
- `coverage` — serinin kendisi tam mı; beklenen/gözlenen örneklem, en uzun boşluk ve **o
  boşluğun nerede olduğu**

Uptime kapsama değildir: uç kısa sayfa döndürdüğünde heartbeat "ok", kapsama "delik var" der.

`--lock-file` ikinci bir toplayıcının aynı anda başlamasını engeller. Bayat kilit otomatik
silinmez; süreç gerçekten ölüyse dosyayı elle kaldırın.

Publisher yalnız exact-hour yolu oluşturur ve mevcut saat dosyasını overwrite etmez. Yeterli
geçmiş varsa `fragility` gerçek veriden üretilir; `direction` **her koşulda** null kalır ve
yön kapısı `unavailable` olur (`direction_rules_unavailable`). Geçmiş yetersizse ilgili
feature `feature_unavailable:<feature>:<neden>` blocker'ı yazar. `radar-signal` her iki
durumda da deterministik `WAIT` verir. Scheduler/supervisor bu dilimde yoktur.

Faz durumu: **1e — spot geçmişi + collector coverage** (ADR-0008). `get_health`,
`get_derivatives`, backfill/collect/publish/run/status çalışır; yön kuralı, rejim
sınıflandırması, alarm/bildirim ve çok-kaynak kapsamı Faz 1'in devamıdır (SPEC §4, §7).
