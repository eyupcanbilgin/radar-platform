# WP-0001 Bağımsız İnceleme Devri

**İş paketi:** Araştırma Kapısı Onarımı
**Dal:** `feature/eleme-tezgahi`
**İnceleme türü:** Kod, yöntem ve kanıt kapısı
**Yazarın yetkisi:** İnceleme kaydını yazar oluşturamaz veya onaylayamaz.

## Amaç

Bu inceleme yeni bir trading avantajını veya kârlılığı onaylamaz. Amaç, geri çekilen eski
eleme raporunun yerine Development verisinde çalışacak `pulse-v2.0` yönteminin teknik olarak
doğru ve kanıt üretmeye hazır olup olmadığını değerlendirmektir.

İnceleme geçse bile sonuçlar `Development` düzeyindedir. Locked OOS açılmaz, gerçek emir
üretilmez ve herhangi bir hipotez otomatik olarak `accepted` olmaz.

## İnceleme kapsamı

Özellikle şu noktalar kod ve testlerle çapraz kontrol edilmelidir:

1. Null dağılımının test edilen getiri ufkuyla eşleşmesi ve circular moving-block bootstrap.
2. Örtüşen ileri getiriler için olayların deterministik, örtüşmesiz seçimi.
3. `greater`, `less` ve `two-sided` alternatiflerinin sonuç görülmeden sabitlenmesi.
4. Yalnız sonlu p-değerlerinin Benjamini-Hochberg evrenine alınması.
5. Funding, hafta sonu ve yüksek-vol olaylarının epizot başlangıcında tekilleştirilmesi.
6. Karar mumu kapandıktan sonraki mum açılışının giriş referansı olması ve ufuk hizalaması.
7. Bir barlık volatilitenin tanımlı kalması ve forward veri sızıntısı olmaması.
8. Londra/New York seanslarının timezone/DST davranışı.
9. Registry verdict düzeltmelerinin eski deney satırlarını değiştirmeden append-only olayla
   uygulanması ve son geçerli olayın etkin verdict olması.
10. `2026-08-04` end-exclusive sınırının locked OOS verisine erişimi engellemesi.
11. Üretilen raporun eski bulguları canlandırmaması veya Development sonucunu final kanıt
    gibi sunmaması.

## İnceleme komutları

`services/radar-signal` dizininde:

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/run_pulse_reanalysis.py `
  --allow-dirty-smoke --permutations 50 --out var/reviewer-smoke.json
```

İncelenen signal commit'inin kapının kullandığı 12 karakterli SHA'sı şu komutla alınır:

```powershell
$signalCommit = git log -1 --format=%H -- .
$signalCommit.Substring(0, 12)
```

## Onay kaydı

İnceleme gerçekten bağımsız tamamlanır ve bütün kontroller geçerse incelemeci aşağıdaki
biçimde `docs/reviews/2026-08-04-wp0001/pulse-v2-review.json` dosyasını oluşturur. Dosya,
incelenen signal commit'inin 12 karakterli SHA'sına bağlanır ve ayrı bir commit olarak
kaydedilir. `checks` alanlarından biri doğrulanmadıysa `true` yazılmaz ve resmî koşu açılmaz.

```json
{
  "schema_version": "1",
  "reviewed_commit": "<12-karakter-signal-sha>",
  "reviewer": "<incelemeci-kimliği>",
  "reviewed_at_utc": "<ISO-8601 UTC>",
  "verdict": "approved",
  "independent": true,
  "checks": {
    "statistics": true,
    "locked_oos": true,
    "registry": true,
    "reporting": true
  },
  "notes": "<kısa inceleme özeti>"
}
```

Reddedilen veya düzeltme isteyen inceleme `approved` kaydı üretmez. Düzeltme yapılırsa SHA
değişeceğinden yeni commit yeniden incelenir.

## İnceleme sonrası

Onay kaydı commit'lenip çalışma ağacı temizlendikten sonra resmî Development yeniden analizi:

```powershell
make pulse-reanalysis
```

Bu komut manifest, tüm repo temizliği, locked-OOS sınırı ve commit'e bağlı bağımsız inceleme
kaydını birlikte doğrular.
