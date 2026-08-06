# ADR-0032 — F-0001 Saatlik Runtime Bağlantısı

- **Tarih:** 6 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0030, ADR-0031

## Karar

1. Mevcut `run_hourly_decision.py` one-shot/daemon süreci, açık
   `--f0001-baseline-contexts` argümanı verildiğinde aynı saatte ledger'a kaydettiği immutable
   context payload'ını F-0001 forward trigger defterine de gönderir. İkinci bir saat seçici
   veya scheduler kurulmaz.
2. Entegrasyon opt-in'dir. `--f0001-trigger-ledger` tek başına kullanılamaz ve `--as-of`
   replay modu baseline argümanıyla birlikte kesin olarak reddedilir.
3. Ön-kayıt başlangıcından önce runtime `before_start` döndürür ve yazmaz. Exact-hour context
   yoksa `context_unavailable` döndürür; sonradan backfill yapmaz. Sonraki başarılı saat
   eksik aralığı defter blocker'ı olarak taşır.
4. Baseline set başlangıçta bir kez manifest/hash/Locked OOS kapısından geçer. Her saat aynı
   karar ledger'ındaki context kullanılır; dosya ikinci kez farklı semantikle okunmaz.
5. Forward gözlem hatası sessizce yutulmaz. Saatlik karar/outbox daha önce yazılmışsa süreç
   retry'da aynı kararı okuyup exact context ile trigger defterindeki crash gap'ini onarabilir.

## Sonuç

Forward coverage, mevcut paper saat ritmine opt-in bağlanmıştır; gerçek ilk kayıt ön-kayıt
başlangıcından önce yapılmamıştır. Bu bağlantı outcome, Registry, alert veya direction açmaz.
