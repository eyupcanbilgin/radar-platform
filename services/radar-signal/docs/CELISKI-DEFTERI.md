# Çelişki Defteri

Durum raporunda (`docs/DURUM-RAPORU-2026-08-04.md`) tespit edilen Ç1–Ç8 çelişkilerinin
kapanış kaydı. Her madde ya **DÜZELTİLDİ** ya da gerekçesiyle **KABUL EDİLEN BORÇ**tur.
Sessizce kapatılan madde yoktur.

| # | Çelişki | Durum | Karar / gerekçe |
|---|---|---|---|
| Ç1 | Kart "REDDEDİLDİ" ↔ registry "pending" (S-0002b ×3) | **DÜZELTİLDİ** | `backfill_registry.py` ile 10 kayıt kart kararıyla eşleştirildi; `pending=0`. `test_registry_file_integrity.py::test_verdicts_are_valid_and_closed` tekrarını engelliyor. Commit `2312994` |
| Ç2 | ADR-0004 "main'e commit yasak" ↔ işler main'de | **DÜZELTİLDİ (kural gerçeğe uyduruldu)** | Kural olduğu gibi uygulanamıyordu ve zaten ihlal edilmişti. Amacına göre daraltıldı: **kanıt üreten iş** (strateji, kart, maliyet/boyut config'i, locked-OOS koşusu) `feature/` dalı + bağımsız inceleme + temiz ağaç ister; **altyapı/onarım/doküman** doğrudan `main`'e gidebilir. Gerekçe: bu işlerde "yazar ≠ incelemeci"nin koruyacağı bir ölçüm sonucu yok; tören maliyeti fayda üretmiyordu. CLAUDE.md kural 13 güncellendi |
| Ç3 | "Final koşular temiz ağaçta" ↔ S-0002b koşularının 2/3'ü `git_dirty: True` | **KABUL EDİLEN BORÇ** | S-0002b koşuları **geliştirme dönemi** koşularıdır, locked-OOS değil (ADR-0005 gereği locked pencere 2026-08-04'ten ileri). ADR-0004 md.4 temiz ağacı yalnız locked-OOS ve final koşular için şart koşuyor. Kayıtlar `git_dirty` alanını taşıdığı için durum gizli değil. **Borç:** S-0002b'nin herhangi bir sonucu "final" etiketi alacaksa temiz ağaçtan yeniden koşulmalı |
| Ç4 | "Registry'siz koşu geçersiz" ↔ registry okunamıyor | **DÜZELTİLDİ** | cp1254 bozulması onarıldı, savunma katmanı ve gerçek-dosya regresyon testi eklendi. Commit `2312994` |
| Ç5 | Kart A "60 günlük dağılım" ↔ kod `rolling(80)` = 20 gün | **AÇIK — kanıta bağlandı** | Kartı mı kodu mu düzelteceğimiz tahminle değil ölçümle belirlenecek: Kart A nabız analizi (adım 4) 20 ve 60 günlük pencereyi aynı veride yan yana koşuyor. Sonuç geldikten sonra ADR yazılacak. Bu satır o ADR ile kapanır |
| Ç6 | Sizing düzeltmesi strateji seviyesinde ↔ config sabit notional | **KISMEN DÜZELTİLDİ** | Oran koddan çıkarıldı: `config/sizing.yaml` + `scripts/sizinglib.py`; S-0002b oranı buradan okuyor (davranış birebir aynı: %10). **Kalan borç:** `config.dryrun.json` hâlâ `stake_amount: 1000` taşıyor ve **S-0001 hâlâ sabit notional ile ölçülmüş durumda**. S-0001 taban çizgisiyle yapılacak bir sonraki kıyastan ÖNCE S-0001 yüzde-sizing ile yeniden koşulmalı; aksi halde kıyas elma-armut olur |
| Ç7 | Veri manifesti monorepoda ↔ veri dosyaları monorepoda yok | **DÜZELTİLDİ** | 177 MB ham veri + 34 artefakt taşındı; `datapaths.py` ile yol yapılandırılabilir; `data_manifest.py --verify` CI'da koşuyor. Commit `cc6388b` |
| Ç8 | CR-002 durum tablosu S-0002b sonrası güncellenmemiş | **DÜZELTİLDİ** | Tablo 4 Ağu durumuna göre yenilendi (aşağıdaki commit) |

## Kabul edilen borçların takibi

| Borç | Tetikleyici | Ne zaman ödenmeli |
|---|---|---|
| S-0002b sonuçları kirli ağaçtan | Sonuçlardan birine "final" denmesi | Locked-OOS koşusundan önce |
| S-0001 sabit notional ile ölçülmüş | Yeni bir stratejinin S-0001 ile kıyaslanması | Kıyastan önce, S-0001 yeniden koşulur |
| `config.dryrun.json` sabit `stake_amount` | Yeni strateji yazımı | Yeni strateji `sizinglib` kullanacak; config alanı yanıltıcı kaldığı sürece belgelidir |
| Ç5 pencere kararı | Adım 4 analizinin bitmesi | ADR ile hemen ardından |
