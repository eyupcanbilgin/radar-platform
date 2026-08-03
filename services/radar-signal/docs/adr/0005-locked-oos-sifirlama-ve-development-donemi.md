# 0005 — Locked Out-of-Sample (OOS) Penceresinin Sıfırlanması ve İleri Tarihli Ayrılması

* **Tarih:** 4 Ağustos 2026
* **Durum:** KABUL EDİLDİ
* **Karar Vericiler:** Eyüpcan, Claude Code, Antigravity

## Bağlam ve Problem
CLAUDE.md Değiştirilemez Kurallar #7 uyarınca *"Locked-test dönemi hyperopt'a ve göz kararı iterasyona kapalıdır; bir kez açılır. Açıldıktan sonra strateji değişirse eski OOS sonucu final etiketi alamaz."*

S-0002 ilk uygulamasında `2026-02-03` → `2026-08-03` dönemi locked-test olarak açılmış, ancak 4 Ağustos 2026 tarihli bağımsız incelemede kural sapmaları (1 ATR sabit stop yerine trailing stop yapılması, saat-dilimi koşullaması eksikliği, funding/perp-spot filtresi eksikliği) ve ölçüm bozulması (sermaye tükenmesi) tespit edildiğinden test **GEÇERSİZ (INVALID)** ilan edilmiştir. 

Açılmış olan bu OOS penceresi yandığı için düzeltilmiş `S-0002b` aynı tarih aralığında locked OOS olarak koşulamaz.

## Karar
1. **Dönem Yeniden Sınıflandırması:** `2026-02-03` → `2026-08-03` tarih aralığı, ölçüm ve kural hatalarından dolayı "Locked OOS" niteliğini kaybetmiş olup **Geliştirme / Geçmiş Doğrulama (Development Extension)** dönemi olarak yeniden tanımlanmıştır.
2. **Yeni Locked OOS Penceresi:** `S-0002b` ve gelecek stratejiler için locked-test penceresi `2026-08-04` tarihinden itibaren ileri yönlü karantina dönemi (Forward Quarantine) olarak ayrılmıştır.
3. **Karantina Bitim Koşulu:** Yeni locked pencere zamana değil fırsata ve rejime bağlıdır (CR-002 P1-3): Minimum 4 hafta AND minimum 100 sinyal AND minimum 2 farklı rejim tamamlanmadan locked OOS kilidi açılamaz.

## Sonuçlar
- `2026-02-03` → `2026-08-03` verileri `S-0002b` için geliştirme ve parametre doğrulama aşamasında kullanılabilir.
- `S-0002b` geliştirildikten sonra yalnız yeni locked OOS karantina penceresinde bir kez nihai teste tabi tutulacaktır.
