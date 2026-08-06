# ADR-0025 — F-0001 Context-Set Manifest Kapısı

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0024, MCP ADR-0010, Platform ADR-0005

## Karar

F-0001 runner artık context klasörlerini ham JSON koleksiyonu olarak kabul etmez. Her klasör
platform `f0001-context-set/v1` manifestini taşımalı; hypothesis, beklenen variant, Locked OOS
sınırı, dosya sayısı, göreli yollar ve SHA-256 değerleri bire bir doğrulanmalıdır. Ana setin
ablation adıyla tekrar verilmesi, dosya ekleme/çıkarma ve içerik değişikliği fail-closed durur.
Doğrulanan üç manifestin SHA-256 değerleri evidence artefaktına ve event-row provenance'ına
bağlanır; doğrulama geçici bir çalışma adımı olarak kaybolmaz.

## Sonuç

Leave-one-family-out raporu klasör adına veya operatör beyanına değil, MCP'nin mühürlediği
counterfactual üretim artefaktına bağlanır. Direction ve gerçek ölçüm durumu değişmez.
