# btc-radar-mcp

Bitcoin merkezli kripto piyasa analizi için **salt-okunur** FastMCP sunucusu. Emir göndermez,
borsa hesabına bağlanmaz, yatırım tavsiyesi üretmez. Skorlama deterministiktir; yorum LLM'e aittir.

Ayrıntılar: [SPEC.md](SPEC.md) (işlevsel şartname) ve [CLAUDE.md](CLAUDE.md) (çalışma kuralları).

## Kurulum ve çalıştırma

```bash
uv sync            # bağımlılıklar + venv
uv run btc-radar   # stdio üzerinde MCP sunucusu
```

Claude Desktop yapılandırması:

```json
{
  "mcpServers": {
    "btc-radar": {
      "command": "uvx",
      "args": ["--from", "C:/Users/TKA/Desktop/btc-radar", "btc-radar"]
    }
  }
}
```

## Geliştirme

```bash
uv run pytest                                  # testler
uv run ruff check --fix && uv run ruff format  # lint + format
uv run python scripts/verify_endpoints.py      # canlı endpoint doğrulaması (smoke)
```

Faz durumu: **0 — iskelet** (`get_health` aracı + config yükleme). Araç seti ve provider'lar
Faz 1'de eklenecek (SPEC §4, §7).
