# ADR-0005 — F-0001 Context-Set Sözleşmesi

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **Etkilenen:** btc-radar-mcp, radar-signal

## Karar

MCP'nin tarihsel ana ve leave-one-family-out context çıktıları ile Signal kanıt runner'ı
arasındaki sınır `contracts/f0001-context-set-v1.schema.json` ile sürümlenir. Variant kimliği,
hariç tutulan feature, Development/Locked OOS sınırı ve context dosya hash'leri veri
sözleşmesinin parçasıdır. MCP sınırı üretir ve kural içeriğiyle birlikte mühürler; Signal
yeniden doğrular ve manifest hash'lerini nihai evidence provenance'ına taşır.

İki servis aynı Locked OOS tarihini kendi paketlenebilir config'lerinde taşır ve CI sözleşme
testi sapmayı reddeder. Sınır CLI parametresiyle ileri alınamaz.
