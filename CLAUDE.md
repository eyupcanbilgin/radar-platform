# CLAUDE.md — radar-platform

Bu depo iki bağımsız çalışma zamanı bileşenini tek monorepoda tutar.

## Kapsam yönlendirmesi

- `services/btc-radar-mcp/` altında çalışmadan önce o klasördeki `SPEC.md` ve
  `CLAUDE.md` dosyalarını oku.
- `services/radar-signal/` altında çalışmadan önce o klasördeki `SINYAL-SPEC.md` ve
  `CLAUDE.md` dosyalarını oku.
- İki servisi etkileyen sözleşme değişikliklerini `contracts/` altında sürümle ve
  `docs/adr/` altında platform ADR'ı ile açıkla.

## Platform kuralları

1. Hiçbir bileşen gerçek borsa emri göndermez.
2. Secret, `.env`, ham piyasa verisi, backtest artefaktı ve çalışma zamanı veritabanı
   Git'e girmez.
3. Servislerin bağımlılık ve lock dosyaları ayrı kalır.
4. Ortak kod çıkarmadan önce sürümlü veri sözleşmesi tercih edilir.
5. Bir servisteki değişiklik en az o servisin test ve lint kapılarını geçer; sözleşme
   değişikliği iki servisin entegrasyon testini de gerektirir.

