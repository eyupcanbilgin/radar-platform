# ADR-0010 — BTC 1h Karar Sonuç Değerlendiricisi ve Append-Only Outcome Defteri

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0008, Platform ADR-0003, `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 1

## Bağlam

ADR-0008 BTC 1h teknik feature snapshot'larını ve her saat üretilen `DecisionCardV1` kartlarını `DecisionLedger` içinde değişmez olarak saklamayı sağladı. Ancak kararların zaman içindeki getirileri (`+1h`, `+4h`, `+24h`), MFE (Maximum Favorable Excursion), MAE (Maximum Adverse Excursion) ve veri sağlığı durumları otomatik kaydedilmiyordu.

Kararların maliyet sonrası sonuçlarını ölçmek Hedefe Geliştirme Planı Faz 1'in temel kabul koşuludur. Bu ölçüm yapılırken mevcut canlı `hourly_decisions` satırlarının değiştirilmemesi, eksik/bozuk veriler için hayalî zero-return uydurulmaması ve `WAIT` kararının nötr getiri gibi algılanmaması gerekir.

## Karar

1. **Ayrı Append-Only Outcome Defteri (`decision_outcomes`):**
   Mevcut `hourly_decisions` ve `feature_snapshots` tablolarına dokunulmaz. Karar sonuçları `DecisionLedger` veritabanı içerisinde ayrı `decision_outcomes` tablosunda saklanır. `decision_outcomes_no_update`, `decision_outcomes_no_delete` ve `decision_outcomes_no_conflicting_insert` SQLite trigger'ları ile silme, güncelleme ve çakışan eklemeler kesin olarak engellenir.

2. **Ufuk Değerlendirmesi (+1h, +4h, +24h):**
   Her `DecisionCard` için `+1h`, `+4h` ve `+24h` ufukları ayrı bağımsız outcome kartları (`DecisionOutcomeV1`) olarak değerlendirilir.
   - Referans giriş fiyatı ($P_{ref}$): Karar anını takip eden ilk muma ait `open` fiyatıdır.
   - Ufuk kapanış fiyatı ($P_{end}$): Ufuk sonundaki muma ait `close` fiyatıdır.

3. **Veri Sağlığı ve Ufuk Süresi Koruması:**
   Yalnız kapanmış ve `available_at_utc <= horizon_close_utc` şartını sağlayan public mumlar kullanılır.
   - Henüz dolmamış gelecek ufuklar `status="pending"` olarak bırakılır.
   - Eksik mum, kopuk zaman serisi (gap) veya yayın zamanı uymayan durumlarda `status="unavailable"` kaydedilir; kesinlikle sıfır getiri veya ileriye taşıma (forward-fill) uydurulmaz.

4. **Semantik Idempotency ve Conflict Koruması:**
   Outcome kimliği `OUT-` ön eki ile `sha256_hex({"decision_id": decision_id, "horizon": horizon, "evaluator_version": evaluator_version})[:16]` biçiminde deterministik türetilir. Aynı verilerle tekrar değerlendirme yapıldığında işlem idempotenttir (`record_outcome` `False` döner). Aynı kimlikle farklı outcome içeriği yazılmak istendiğinde `ImmutableDecisionError` ile işlem engellenir.

5. **WAIT Birinci Sınıf Semantiği:**
   `WAIT` çıktısında yönsel PnL (`raw_return`, `net_return`, `mfe`, `mae`) üretilmez (`None`). Karar anındaki piyasa hareketi açık bir `opportunity_return` $= (P_{end} - P_{ref}) / P_{ref}$ gözlemi olarak kaydedilir.

6. **LONG / SHORT Matematiği ve Maliyet Entegrasyonu:**
   - `LONG`: $R_{raw} = (P_{end} - P_{ref}) / P_{ref}$, $MFE = (\max(H) - P_{ref}) / P_{ref}$, $MAE = (\min(L) - P_{ref}) / P_{ref}$
   - `SHORT`: $R_{raw} = (P_{ref} - P_{end}) / P_{ref}$, $MFE = (P_{ref} - \min(L)) / P_{ref}$, $MAE = (P_{ref} - \max(H)) / P_{ref}$
   - Net getiri hesaplanırken `config/costs.yaml` sözleşmesinden komisyon (taker) ve kayma çekilir. Maliyet konfigürasyonu yoksa veya eksikse `net_return = None` bırakılır.

7. **Güvenli CLI:**
   `scripts/evaluate_decision_outcomes.py` komut satırı aracı yalnız süresi dolmuş kararları toplu işler; sınırsız geçmiş taraması yapmaz.

## Sonuçlar

Sistem artık paper ortamda üretilen tüm kararların 1h, 4h ve 24h sonraki gerçek sonuçlarını, MFE/MAE oynaklık alanlarını ve veri eksikliklerini değişmez biçimde kaydeder. Canlı kararları değiştirmez, WAIT kararlarında yönsel getiri uydurmaz ve geçmişe dönük look-ahead sızıntılarını engeller.
