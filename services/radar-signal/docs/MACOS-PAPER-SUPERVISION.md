# macOS Paper Runtime Supervision

Bu runbook dört paper sürecini `launchd` ile çalıştırır: MCP producer, saatlik WAIT karar
runtime'ı, outbox pump ve salt-okunur F-0001 coverage reporter. Gerçek emir/private API key
yoktur. İlk kurulumda `console` modu kullanın; Telegram ayrı credential kontrolünden sonra
açılır.

## Ön koşullar

1. Çalışma için günlük geliştirme klasöründen ayrı, temiz bir checkout hazırlayın. Runtime
   provenance kapısı untracked dosya dahil kirli checkout'u reddeder.
2. MCP ve Signal için bağımlılıkları kurulu iki açık Python executable yolu hazırlayın.
3. Ayrı state root altında mevcut PIT ve mühürlü combined baseline'ı yerleştirin:

```text
STATE_ROOT/
  mcp/pit.sqlite
  signal/f0001-contexts/combined/context-set.json
  signal/f0001-contexts/combined/v1/...
```

Combined manifest SHA-256 değeri `config/f0001_forward_observation.yaml` ile aynı olmalıdır.
Araç bu kapıyı kendisi doğrular.

## Plist üretimi

```bash
SIGNAL_PYTHON=/absolute/path/to/radar-signal-python
MCP_PYTHON=/absolute/path/to/btc-radar-mcp-python
CHECKOUT_ROOT="${HOME}/Library/Application Support/Radar/runtime-checkout"
STATE_ROOT="${HOME}/Library/Application Support/Radar/state"

"${SIGNAL_PYTHON}" services/radar-signal/scripts/render_macos_launch_agents.py \
  --checkout-root "${CHECKOUT_ROOT}" \
  --state-root "${STATE_ROOT}" \
  --mcp-python "${MCP_PYTHON}" \
  --signal-python "${SIGNAL_PYTHON}" \
  --delivery-mode console \
  --output-dir "${STATE_ROOT}/launchagents"
```

Araç yalnız plist üretir. Dört dosyayı `plutil -lint` ile doğruladıktan sonra kullanıcı
LaunchAgents klasörüne kopyalayın ve yükleyin:

```bash
mkdir -p "${HOME}/Library/LaunchAgents"
cp "${STATE_ROOT}"/launchagents/com.radar.*.plist "${HOME}/Library/LaunchAgents/"
launchctl bootstrap "gui/${UID}" "${HOME}/Library/LaunchAgents/com.radar.mcp-producer.plist"
launchctl bootstrap "gui/${UID}" "${HOME}/Library/LaunchAgents/com.radar.signal-hourly.plist"
launchctl bootstrap "gui/${UID}" "${HOME}/Library/LaunchAgents/com.radar.signal-pump.plist"
launchctl bootstrap "gui/${UID}" "${HOME}/Library/LaunchAgents/com.radar.signal-coverage.plist"
```

## Doğrulama ve geri alma

```bash
launchctl print "gui/${UID}/com.radar.mcp-producer"
launchctl print "gui/${UID}/com.radar.signal-hourly"
launchctl print "gui/${UID}/com.radar.signal-pump"
launchctl print "gui/${UID}/com.radar.signal-coverage"
```

MCP `status`, `STATE_ROOT/signal/f0001-forward-coverage.json` ve `STATE_ROOT/signal/logs`
birlikte incelenir. Coverage JSON içindeki `status` ve `blockers` alanları okunmadan yalnız
dosyanın varlığı sağlık sayılmaz. Process
ayakta görünürken coverage delikliyse sistem sağlıklı sayılmaz.

Geri almak için önce dört agent'ı `launchctl bootout gui/${UID}/<plist-yolu>` ile durdurun.
State veritabanlarını silmeyin; append-only kanıt ve pending outbox korunmalıdır.
