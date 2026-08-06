# ADR 0010 — F-0001 Tarihsel Context Setleri

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** MCP ADR-0005, Signal ADR-0024, Platform ADR-0005, F-0001

## Kararlar

1. `btc-radar-producer research-contexts`, PIT deposundan her UTC saat için üç ayrı set
   üretir: `combined`, `without_funding_stress`, `without_oi_buildup`.
2. Counterfactual setler yalnız ilgili config kuralını çıkarır; eşikler ve diğer kurallar
   değişmez. Eksik kalan feature nötr değere çevrilmez. Direction her koşulda null kalır.
3. Her variant ayrı snapshot deposu kullanır. Snapshot kimliği mevcut canlı sözleşmede kural
   variantını taşımadığından tek depoyu paylaşmak aynı kimlik/farklı evidence çakışmasına yol
   açabilirdi.
4. Her set `f0001-context-set/v1` manifestiyle variant, hariç tutulan feature, saat sınırları
   kural içeriğinin SHA-256 değerini ve her context dosyasının SHA-256 değerini taşır. Signal
   klasör adına güvenmez; manifesti ve hash'leri doğrular.
5. Locked OOS sınırı CLI'dan gevşetilemez; paketlenen `config/f0001_context_sets.yaml`
   otoritesidir ve Signal ön-kayıt config'iyle sözleşme testinde eşleşir.
6. Tarihsel üretimde `computed_at=end_exclusive` sabittir; aynı PIT ve config ile yeniden
   koşu bit-bit aynı context ve manifestleri üretir.

## Sonuçlar

Gerçek F-0001 koşusunun ana ve ablation context girdileri yeniden üretilebilir ve türü
kanıtlanabilir hale gelir. Ham PIT verisi repoya girmez; bu ADR sonuç/verdict üretmez.
