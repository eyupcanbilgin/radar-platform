# macOS Paper Runtime Supervision

Bu runbook **altı** paper sürecini `launchd` ile çalıştırır. Gerçek emir ve private API key
yoktur. İlk kurulumda `console` modu kullanın; Telegram ayrı credential kontrolünden sonra
açılır.

| Agent | Tür | Ne yapar | Kanıt/çıktı |
|---|---|---|---|
| `com.radar.mcp-producer` | daemon | Binance public veriyi PIT'e toplar, kapanan saat için context yayınlar | `mcp/pit.sqlite`, `mcp/heartbeat.sqlite`, `signal/decision-context/` |
| `com.radar.signal-hourly` | daemon | Kapanan saat için değişmez `WAIT` kararı ve F-0001 forward gözlemi yazar | `signal/hourly-decisions.sqlite`, `signal/f0001-forward-triggers.sqlite` |
| `com.radar.signal-pump` | daemon | Outbox'taki mesajları console/Telegram'a teslim eder | `signal/outbox.sqlite` |
| `com.radar.signal-coverage` | periyodik | Forward defterinin kapsamasını raporlar | `signal/f0001-forward-coverage.json` |
| `com.radar.signal-health-alert` | periyodik | **Duran ilerlemeye** uyarı üretir (ADR-0042) | `signal/runtime-health.json` + outbox |
| `com.radar.signal-readiness` | periyodik | "Ne zaman ölçülebilir?" projeksiyonu (ADR-0047) | `signal/f0001-readiness-projection.json` |

Periyodik ajanlar tek-seferliktir: `launchctl print` çıktısında **`not running` normaldir**.
Sağlık kanıtı `last exit code` ve çıktı dosyasının tazeliğidir.

## Ön koşullar

1. Günlük geliştirme klasöründen ayrı, **temiz** bir checkout. Runtime provenance kapısı
   untracked dosya dahil kirli checkout'u reddeder.
2. MCP ve Signal için iki açık Python executable yolu. Renderer `venv/bin/python` symlink
   yolunu plist'te aynen korur; ana Homebrew interpreter yoluna çözülmüş plist geçersiz
   kurulum belirtisidir (ADR-0038).
3. Ayrı state root altında mevcut PIT ve mühürlü combined baseline:

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
"${SIGNAL_PYTHON}" services/radar-signal/scripts/render_macos_launch_agents.py \
  --checkout-root "${CHECKOUT_ROOT}" \
  --state-root "${STATE_ROOT}" \
  --mcp-python "${MCP_PYTHON}" \
  --signal-python "${SIGNAL_PYTHON}" \
  --delivery-mode console \
  --output-dir "${STATE_ROOT}/launchagents"
```

Araç yalnız plist üretir, kurmaz.

**Güncelleme yaparken önce diff alın.** Üretilen plist'i kuruludan farklı olup olmadığına
bakmadan kopyalamak, çalışan bir servisi sessizce değiştirebilir:

```bash
for p in "${STATE_ROOT}"/launchagents/com.radar.*.plist; do
  name=$(basename "$p")
  diff <(plutil -p "${HOME}/Library/LaunchAgents/${name}" 2>/dev/null) <(plutil -p "$p") \
    >/dev/null 2>&1 && echo "${name}: fark yok" || echo "${name}: FARK VAR"
done
```

Yalnız farkı olan plist'i kopyalayın ve **yalnız onu** yeniden yükleyin. Argüman değişmediyse
`kickstart -k` yeter; argüman değiştiyse `bootout` + `bootstrap` gerekir.

```bash
cp "${STATE_ROOT}"/launchagents/com.radar.*.plist "${HOME}/Library/LaunchAgents/"
for a in mcp-producer signal-hourly signal-pump signal-coverage signal-health-alert signal-readiness; do
  launchctl bootstrap "gui/${UID}" "${HOME}/Library/LaunchAgents/com.radar.${a}.plist"
done
```

## Teslimatı durdurma — kill-switch (ADR-0049)

Teslimatı durdurmak için **daemon öldürmeyin**. Anahtar bir dosyadır; **varlığı** teslimatı
durdurur:

```bash
echo "gerekçe: kart metni yanlış" > "${STATE_ROOT}/signal/delivery.pause"   # DURDUR
rm "${STATE_ROOT}/signal/delivery.pause"                                   # DEVAM ET
```

- Mesaj **kaybolmaz**: outbox'ta `PENDING` bekler, anahtar kalkınca gönderilir.
- İçerik ayrıştırılmaz — dosyaya `false` yazmak da durdurur. Yazdığınız metin pump logunda
  gerekçe olarak görünür.
- Dosya okunamıyorsa da durulur: bir durdurma kontrolünde belirsizlik **durma** yönünde çözülür.
- Anahtar yalnız **teslimatı** durdurur; karar defteri ve forward gözlem kaydı çalışmaya
  devam eder.

## Sağlık nasıl okunur

**`running` sağlık kanıtı değildir.** 9–10 Ağustos 2026'da dört ajan da `running` görünürken
forward defteri 17 saat boyunca ilerlemedi (ADR-0041). Sırayla şunlara bakın:

```bash
# 1. İlerliyor mu? (duran duruma değil, duran İLERLEMEYE bakılır)
cat "${STATE_ROOT}/signal/runtime-health.json"      # healthy, active_incidents

# 2. Ne kadar birikti?
cat "${STATE_ROOT}/signal/f0001-forward-coverage.json"   # recorded/available/triggered

# 3. Ne zaman ölçülebilir olur?
cat "${STATE_ROOT}/signal/f0001-readiness-projection.json"  # binding_constraint, eta

# 4. Producer geride mi?
python -m btc_radar.producer status --pit-db ... --heartbeat-db ...   # hours_behind
```

`coverage.status` **kalıcı olarak `degraded`dır** (kurulum öncesi saatler doldurulamaz) ve tek
başına arıza göstergesi **değildir**. Arıza göstergesi `runtime-health.json` içindeki
`active_incidents`tir.

### Host uykusu

Runtime, host uyurken **koşmaz**. macOS pilde varsayılan olarak uyur ve bu forward kanıtını
sessizce yok eder. Kalıcı toplama için makine prize takılı ve uyanık olmalıdır
(AC güçte `pmset` `sleep 0`). Kapak kapatmak ekranı kapatıp uyku tetikler.

Uyandıktan sonra producer ve Signal aynı anda devam eder; aradaki grace sıralaması yaşanmaz.
Bu yüzden Signal, kararı yazmadan önce context'i sınırlı süre bekler (ADR-0041).

## Geri alma

```bash
for a in mcp-producer signal-hourly signal-pump signal-coverage signal-health-alert signal-readiness; do
  launchctl bootout "gui/${UID}/com.radar.${a}"
done
```

**State veritabanlarını silmeyin.** Append-only kanıt (karar defteri, forward defteri,
Registry) ve pending outbox korunmalıdır. Geçmiş saat eklemeyin: kaçan saat blocker olarak
kalır, backfill edilmez (ADR-0040).
