# Platform mimarisi

```text
btc-radar-mcp
  public piyasa kaynakları -> doğrulama -> değişmez snapshot/rejim bağlamı
                                      |
                                      v
radar-signal
  kapanmış 1h mum -> FeatureSnapshot --+
                                         +-> LONG / SHORT / WAIT -> DecisionLedger
  decision-context/v1 ------------------+
                                         +-> yönsel aday varsa SignalLedger/outbox
```

İki bileşen aynı repoda geliştirilir fakat ayrı süreçler ve ayrı bağımlılık ortamları
olarak çalışır. MCP piyasa bağlamından, sinyal servisi strateji/backtest ve bildirim
yaşam döngüsünden sorumludur.

Platform seviyesindeki entegrasyon sürümlü bir sözleşme üzerinden yapılır; bir
servisin diğerinin iç Python modüllerini doğrudan import etmesi hedeflenmez.
