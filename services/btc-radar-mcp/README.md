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

## PIT toplama ve signal context yayını

Toplama ile yayın bilinçli olarak ayrıdır: kapanıştan sonra çekilen değer geçmiş saate
backdate edilmez.

```bash
# Bir kereye mahsus geçmiş: settled funding + saatlik OI (API key yok)
uv run btc-radar-producer backfill \
  --pit-db ./var/pit.sqlite --funding-days 120 --open-interest-days 30

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

Publisher yalnız exact-hour yolu oluşturur ve mevcut saat dosyasını overwrite etmez. Yeterli
geçmiş varsa `fragility` gerçek veriden üretilir; `direction` **her koşulda** null kalır ve
yön kapısı `unavailable` olur (`direction_rules_unavailable`). Geçmiş yetersizse ilgili
feature `feature_unavailable:<feature>:<neden>` blocker'ı yazar. `radar-signal` her iki
durumda da deterministik `WAIT` verir. Scheduler/supervisor bu dilimde yoktur.

Faz durumu: **1b — geçmiş birikimi + kırılganlık kapısı** (ADR-0005). `get_health`,
`get_derivatives`, backfill/collect/publish çalışır; yön kuralı, rejim sınıflandırması ve
çok-kaynak kapsamı Faz 1'in devamıdır (SPEC §4, §7).
