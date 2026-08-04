# Veri manifestleri

Her manifest, o tarihte diskte bulunan ham veri dosyalarının sha256/satır/aralık
fotoğrafıdır. Registry kayıtlarındaki `dataset_snapshot`, koşunun yapıldığı andaki
manifestin `manifest_sha256` değerine işaret eder.

**Manifestler silinmez ve yeniden yazılmaz.** Veri değiştiğinde yeni tarihli manifest
üretilir; eski manifest, ona atıf yapan koşuların kanıtı olarak yerinde kalır.

| Manifest | Kapsam | Not |
|---|---|---|
| `MANIFEST-20260803` | 8 dosya | S-0001, S-0002, S-0002b koşularının `dataset_snapshot`'ı bu manifeste işaret eder (`89f6dbb390dd…`) |
| `MANIFEST-20260804` | 10 dosya | Güncel. `manifest_sha256=6217119a8220…` |

## Bilinen sapma — 20260803 manifesti (4 Ağu 2026'da tespit edildi)

`data_manifest.py --verify` monorepoya taşıma sonrası ilk koşuşunda iki dosyada hash
uyuşmazlığı buldu:

| Dosya | Manifest | Diskte |
|---|---|---|
| `BTC_USDT_USDT-1h-mark.feather` | 57.968 satır | 57.969 satır |
| `ETH_USDT_USDT-1h-mark.feather` | 57.968 satır | 57.969 satır |

**Sebep:** 3 Ağustos akşamı 1m verisi indirilirken mark serilerine birer saatlik mum daha
eklendi; manifest bu indirmeden önce üretilmişti. Tarih aralığı değişmedi
(2019-12-23 → 2026-08-03), yalnız son bar eklendi.

**Etkisi:** Geçmiş koşuların test aralıkları 2026-08-03'te bitiyor, eklenen bar aralığın
sonunda. Sonuçların değiştiğine dair bir gösterge yok, **ancak yeniden koşularak
doğrulanmadı** — bu yüzden sapma "yok sayıldı" değil, "kaydedildi" statüsündedir.

**Karar:** 20260803 manifesti olduğu gibi bırakıldı (geçmiş koşuların referansı),
20260804 manifesti güncel gerçeği yansıtır. Bundan sonraki koşular yeni manifeste
işaret edecek. `--verify` her zaman EN YENİ manifeste bakar; CI bu yüzden yeşildir.
