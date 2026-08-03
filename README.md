# Radar Platform

BTC/ETH piyasa bağlamı üreten salt-okunur MCP servisi ile, bu bağlamı kullanan
intraday sinyal araştırma sistemini tek private monorepoda bir araya getirir.
Sistem gerçek borsa emri göndermez.

## Bileşenler

- `services/btc-radar-mcp/`: FastMCP tabanlı piyasa/rejim servisi.
- `services/radar-signal/`: Freqtrade dry-run tabanlı sinyal, backtest ve bildirim hattı.
- `contracts/`: İki servis arasında paylaşılacak sürümlü veri sözleşmeleri.
- `docs/`: Yalnız platformun tamamını ilgilendiren mimari belgeler.

Her servis kendi bağımlılıklarını, lock dosyasını, konfigürasyonunu ve testlerini
korur. Servise özel geliştirme kuralları ilgili klasördeki `CLAUDE.md` dosyasındadır.

## Yerel geliştirme

```powershell
# MCP
Set-Location services/btc-radar-mcp
uv sync
uv run pytest

# Sinyal motoru (Freqtrade sanal ortamı servis içinde kurulur)
Set-Location ../radar-signal
.venv/Scripts/python -m pytest -q
```

Kökten `make test` ve `make lint`, iki servisin kendi komutlarını sırayla çalıştırır.

## MCP istemci yapılandırması

```json
{
  "mcpServers": {
    "btc-radar": {
      "command": "uvx",
      "args": [
        "--from",
        "C:/Users/TKA/projeler/radar-platform/services/btc-radar-mcp",
        "btc-radar"
      ]
    }
  }
}
```

## Veri ve secret politikası

Ham piyasa verisi, backtest çıktıları, SQLite defterleri, sanal ortamlar ve `.env`
dosyaları Git'e girmez. Veri manifestleri ile Experiment Registry ise araştırma kanıt
zincirinin parçası olarak sürüm kontrolünde tutulur.

