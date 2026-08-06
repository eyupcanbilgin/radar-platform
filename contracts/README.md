# Contracts

Bu klasör `btc-radar-mcp` ile `radar-signal` arasındaki sürümlü veri sözleşmelerine
ayrılmıştır.

Yeni sözleşmeler geriye uyumluluk kuralı, açık sürüm numarası ve iki tarafta fixture
tabanlı sözleşme testiyle eklenmelidir.

## Aktif sözleşmeler

- [`decision-context/v1`](decision-context/v1/README.md): BTCUSDT 1h paper karar döngüsünde
  MCP rejim snapshot'ını signal servisine taşıyan salt-okunur bağlam zarfı.
- [`f0001-context-set/v1`](f0001-context-set-v1.schema.json): F-0001 ana ve iki
  leave-one-family-out tarihsel context setinin variant, sınır ve dosya hash manifesti.
