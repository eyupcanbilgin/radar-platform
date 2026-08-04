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
# Saat boyunca düzenli çalıştırılacak public collector (API key yok)
uv run btc-radar-producer collect --pit-db ./var/pit.sqlite

# Kapanmış tam UTC saat için immutable context yayınla
uv run btc-radar-producer publish \
  --as-of 2026-08-04T12:00:00Z \
  --pit-db ./var/pit.sqlite \
  --snapshot-db ./var/snapshots.sqlite \
  --context-root ../radar-signal/var/decision-context
```

Publisher yalnız exact-hour yolu oluşturur ve mevcut saat dosyasını overwrite etmez. Skor
kuralları boş olduğu sürece geçerli artifact üretir ama yön kapısı `unavailable` kalır;
`radar-signal` bununla deterministik `WAIT` verir. Scheduler/supervisor bu dilimde yoktur.

Faz durumu: **1a — ilk gerçek provider + PIT/context taşıması**. `get_health` ve dar kapsamlı
`get_derivatives` çalışır; çok-kaynak scoring/rejim Faz 1'in devamıdır (SPEC §4, §7).
