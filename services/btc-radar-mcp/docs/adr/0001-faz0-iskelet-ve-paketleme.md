# ADR 0001 — Faz 0 iskeleti: paketleme ve config çözümleme

- **Tarih:** 2026-08-03
- **Durum:** Kabul edildi

## Bağlam

CLAUDE.md `config/` dizinini repo kökünde tutmayı zorunlu kılar; dağıtım hedefi ise
`uvx --from . btc-radar`. uvx paketi wheel'den çalıştırdığında repo kökündeki `config/`
erişilebilir olmayabilir.

## Karar

1. **Build backend: hatchling.** `[tool.hatch.build.targets.wheel.force-include]` ile
   `config/` → `btc_radar/_config` olarak wheel'e gömülür. Kaynak gerçeği repo kökündeki
   `config/`tir; `_config` yalnızca dağıtım kopyasıdır ve git'e girmez.
2. **Config çözüm sırası** (`core/config.py`): `BTC_RADAR_CONFIG_DIR` env → repo kökü
   `config/` → paket içi `_config`. Hiçbiri yoksa `FileNotFoundError` (fail-loud).
3. **uv kurulumu:** geliştirme makinesinde uv, `python -m pip install --user uv` ile
   kurulmuştur; komutlar `python -m uv ...` veya PATH'te ise `uv ...` olarak çalışır.
4. **Canlı doğrulama** `scripts/verify_endpoints.py`'dedir ve `make smoke`un temelidir.
   bitcoin-data.com için host başına istek bütçesi 5'tir (limit 8/saat, 15/gün); CI cron'u
   bu kaynağı `--skip-bitcoin-data` ile atlar.

## Sonuçlar

- `weights.yaml` değişiklikleri hem geliştirmede hem uvx dağıtımında görünür; skor
  izlenebilirliği için `weights_hash` (sha256/12) yanıtlarda taşınır.
- Faz 3'te HTTP transport gelirse config çözüm sırası değişmeden kalır.
