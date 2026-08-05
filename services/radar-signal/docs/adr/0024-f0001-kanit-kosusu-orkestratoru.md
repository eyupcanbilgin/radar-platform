# ADR-0024 — F-0001 Kanıt Koşusu Orkestratörü

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0021, ADR-0022, ADR-0023, F-0001

## Bağlam

F-0001'in event-row üreticisi, kalibrasyon çekirdeği ve iki-venue veri yolları ayrı ayrı
hazırdı. Bunların elle bağlanması yanlış manifest, kirli kod ağacı, eksik ablation veya aynı
kanıt kimliğinin Registry'ye ikinci kez yazılması riskini taşıyordu.

## Karar

1. `scripts/run_f0001_evidence.py`, yalnız temiz git ağacında güncel manifesti doğruladıktan
   sonra context ve iki venue OHLCV girdilerini event-row ve OOF kalibrasyon zincirine verir.
2. Binance futures ve Coinbase spot dosyalarının içerik hash'leri kullanılan manifestte yer
   almak zorundadır. Feather `date` alanı mum açılışıdır; event-row girdisinde kapanış ve
   availability zamanı bir saat sonrası olarak kurulur.
3. Ana context'e ek olarak `without_funding_stress` ve `without_oi_buildup` counterfactual
   context setleri zorunludur. Eksik ablation ile kanıt veya kabul üretilemez.
4. Çıktı atomik `f0001-evidence/v1` artefaktıdır; direction daima null kalır. `passed`,
   `rejected` ve örneklem/veri blocker'lı `unavailable` koşuların tümü Registry'ye yazılır.
5. Aynı `(F-0001, code_sha, dataset_snapshot)` kimliği tekrar koşulursa tarihî satır
   çoğaltılmaz; mevcut deney kimliği döndürülür.
6. Orkestratör Locked OOS sınırını değiştirmez ve ham veriyi Git'e eklemez. Bu ADR gerçek
   sonuç içermez.

## Sonuçlar

Gerçek veri geldiğinde ölçüm tek, denetlenebilir bir kapıdan koşabilir. Mevcut çalışma
alanında ham iki-venue veri ve uzun dönem counterfactual context setleri bulunmadığından
F-0001 kartının sonucu hâlâ **ÖLÇÜLMEDİ** durumundadır.
