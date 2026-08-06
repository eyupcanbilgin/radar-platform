# Veri manifestleri

Her manifest, o tarihte diskte bulunan ham veri dosyalarının sha256/satır/aralık
fotoğrafıdır. Registry kayıtlarındaki `dataset_snapshot`, koşunun yapıldığı andaki
manifestin `manifest_sha256` değerine işaret eder.

**Manifestler silinmez ve yeniden yazılmaz.** Veri değiştiğinde yeni tarihli manifest
üretilir; eski manifest, ona atıf yapan koşuların kanıtı olarak yerinde kalır.

F-0001 için Coinbase spot girdisini üretmek ve ardından iki venue'yu tek manifestte
doğrulamak:

```bash
python scripts/download_coinbase_spot.py --end 2026-08-04T00:00:00Z
python scripts/data_manifest.py
python scripts/data_manifest.py --verify
```

İlk komut private key kullanmaz ve yalnız `[2024-01-01, 2026-08-04)` aralığındaki kapanmış
BTC-USD saatlik mumları yazar. `user_data/` ham verisi git dışındadır. Yeni manifest
oluşturulmadan önce eski manifest dosyalarına dokunulmaz.

Coinbase public geçmişi bazı saatlerde hiç mum döndürmeyebilir. İndirici bunları sahte sıfır
hacimli mumla doldurmaz; eksik saat ve gap sayısını çıktıda bildirir. F-0001 yalnız gap'e
temas etmeyen kesintisiz trailing/ileri pencereleri kullanır (Signal ADR-0026).

Manifest doğrulandıktan sonra F-0001 kanıt koşusu üç context setini birlikte ister: ana
birleşik kırılganlık, funding ailesi çıkarılmış counterfactual ve OI ailesi çıkarılmış
counterfactual. Bu girdiler aynı karar saatlerini ve PIT kurallarını korumalıdır:

Context setleri önce MCP servisinde üretilir; Locked OOS sınırı config'den gelir:

```bash
btc-radar-producer research-contexts \
  --start 2024-01-01T00:00:00Z \
  --end-exclusive 2026-08-04T00:00:00Z \
  --pit-db /path/to/pit.sqlite \
  --snapshot-root /path/to/f0001-snapshots \
  --output-root /path/to/f0001-contexts
```

```bash
python scripts/run_f0001_evidence.py \
  --contexts /path/to/combined-contexts \
  --contexts-without-funding /path/to/without-funding-contexts \
  --contexts-without-oi /path/to/without-oi-contexts \
  --binance-bars user_data/data/binance/futures/BTC_USDT_USDT-1h-futures.feather \
  --coinbase-bars user_data/data/coinbase/spot/BTC_USD-1h-spot.feather
```

Koşu kirli git ağacında, doğrulanmayan manifestte veya eksik ablation ile durur. Aynı kod ve
dataset snapshot'ı yeniden koşmak Registry'ye ikinci satır eklemez.

| Manifest | Kapsam | Not |
|---|---|---|
| `MANIFEST-20260803` | 8 dosya | S-0001, S-0002, S-0002b koşularının `dataset_snapshot`'ı bu manifeste işaret eder (`89f6dbb390dd…`) |
| `MANIFEST-20260804` | 10 dosya | Tarihsel Binance snapshot'ı. `manifest_sha256=6217119a8220…` |
| `MANIFEST-20260806` | 4 dosya | F-0001 iki-venue Development girdisi; yalnız BTC 1h ve Locked OOS öncesi (`60deaf799f19…`) |

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
