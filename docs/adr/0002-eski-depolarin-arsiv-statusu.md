# ADR-0002 — Eski `btc-radar` ve `radar-signal` depolarının arşiv statüsü

- **Tarih:** 4 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0001 (private monorepo birleşimi)

## Bağlam

ADR-0001 ile iki depo `radar-platform` altında birleştirildi, ama kaynak depolar
diskte kaldı:

| Yol | Ne var | Son commit |
|---|---|---|
| `C:/Users/TKA/Desktop/btc-radar` | tam çalışma kopyası + venv | `7f8214a` |
| `C:/Users/TKA/projeler/radar-signal` | tam çalışma kopyası + venv + 177 MB ham veri | `6417cbe` (`feature/s-0002`) |

Bu, aynı dosyanın iki yerde farklı sürümü riskini doğuruyordu. Nitekim 4 Ağustos'ta
monorepodaki registry onarımı yapılırken eski repodaki kopya bozuk kalmaya devam etti;
ayrıca ham veri yalnız eski repoda olduğu için monorepoda backtest koşulamıyordu.

## Karar

1. **Tek doğruluk kaynağı `radar-platform`'dur.** Eski iki depo **ARŞİV / SALT-OKUNUR**
   statüsündedir: içlerinde geliştirme yapılmaz, commit atılmaz, koşu başlatılmaz.
2. **Ham veri ve backtest artefaktları monorepoya taşındı**
   (`services/radar-signal/user_data/`). Eski repolardaki kopyalar artık yedektir,
   referans değildir.
3. **Monorepoda çalışır ortam kuruldu:** `services/radar-signal/.venv`
   (Python 3.12, `requirements.lock`'tan) ve `services/btc-radar-mcp` `uv` ile.
4. **Veri yolu koda gömülmez:** `scripts/datapaths.py` üzerinden çözülür,
   `RADAR_SIGNAL_USERDIR` ortam değişkeniyle override edilebilir.
5. **Silme kararı ertelendi.** Eski depolar en az bir ay daha diskte kalır; monorepo
   uzak depoya push'landıktan ve bir tam koşu döngüsü sorunsuz tamamlandıktan sonra
   silinmeleri ayrıca değerlendirilir. Erken silmek geri dönüşü olmayan tek işlemdir.

## Sonuçlar

- Eski depolarda yapılan hiçbir değişiklik monorepoya yansımaz ve **kaybolmuş sayılır**.
- Eski repolardaki registry kopyası hâlâ cp1254 bozuktur; onarım yalnız monorepoda
  yapıldı. Bu bilinçlidir: arşiv, arızasıyla birlikte o günün fotoğrafıdır.
- `MANIFEST-20260803` ile diskteki veri arasında iki dosyada 1'er satırlık sapma
  tespit edildi ve `docs/data/OKUBENI.md`'ye kaydedildi; geçmiş manifest korundu,
  güncel gerçek için `MANIFEST-20260804` üretildi.
