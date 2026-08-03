# ADR-0001 — Private monorepo birleşimi

- Tarih: 4 Ağustos 2026
- Durum: Kabul edildi

## Bağlam

`radar-signal` ve `btc-radar-mcp` ayrı Git depolarında gelişti. Experiment Registry ve
değişiklik belgeleri mevcut commit SHA'larına referans verdiği için geçmişi yeniden
yazan bir taşıma araştırma kanıt zincirini zayıflatacaktı.

## Karar

İki kaynak geçmiş, yeni `radar-platform` deposuna `git subtree` ile ve `--squash`
kullanılmadan alındı:

- `services/radar-signal`: `6417cbec317c5fd4489a249d26fd3a50d24fb3a9`
- `services/btc-radar-mcp`: `7f8214a489e6a2aa69348523ac8b3642821ee298`

Servislerin bağımlılıkları, lock dosyaları, konfigürasyonları ve çalışma süreçleri ayrı
kalır. Kök seviye yalnız ortak dokümantasyon, CI orkestrasyonu ve sürümlü sözleşmelere
ayrılır.

## Sonuçlar

- Eski commit SHA'ları yeni `main` geçmişinden erişilebilir kalır.
- Eski commitlerde dosyalar kaynak depoların kök yollarında görünür; yeni
  `services/...` yolları import commitlerinden itibaren başlar.
- Dosya bazlı `git blame` eski prefikse otomatik geçmez; gerektiğinde eski SHA üzerinden
  incelenir.
- İki servisin GitHub workflow'ları kök `.github/workflows/` altında çalışır.
- Signal provenance kaydı tüm monorepo yerine signal servis ağacına göre sürümlenir ve
  dirty kontrolü yapar.
