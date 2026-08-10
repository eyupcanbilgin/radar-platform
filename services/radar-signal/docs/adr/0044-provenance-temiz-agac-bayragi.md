# ADR-0044 — `git_dirty` temiz-ağaç bayrağının onarımı

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0003, ADR-0004, Platform ADR-0004, Signal ADR-0043, CLAUDE.md kural 13

## Bağlam

S-0005 ölçümü (ADR-0043) sırasında, kanıt üreten koşuların temiz ağaçta yapılmasını şart koşan
korumanın **fiilen hiçbir şeyi korumadığı** ortaya çıktı.

`environment_fingerprint()` her koşuya `git_dirty` alanı yazar. ADR-0003, Platform ADR-0004 ve
CLAUDE.md kural 13 bu alana dayanır: kanıt üreten koşu `git_dirty: False` olmalıdır.

Ölçülen gerçek (10 Ağustos 2026):

- S-0003 (`E-20260805-084135-e80d0f`, `-084344-eb6141`, `-084520-51861d`), S-0004
  (`E-20260805-110253-4c1b3c`) ve S-0005'in üç koşusunun **hepsi** `git_dirty: true` taşıyor.
- Yalnız `registry/experiments.jsonl` değiştirilip başka hiçbir şeye dokunulmadığında
  `git_is_dirty()` yine `True` dönüyor.

Sebep: `git_is_dirty()` `git status --porcelain -- .` çalıştırır ve bu, koşunun **yazması
beklenen** append-only kanıt kütüklerini de kirlilik sayar. Her gerçek ölçüm Registry'ye satır
yazdığından bayrak hiçbir koşuda `False` olamaz.

Bu, kendi kendini yenen bir kontroldür: gerçekten kirli bir checkout ile tertemiz bir checkout
**aynı** görünür. Koruma var sanılır, yoktur.

## Kararlar

### 1. Kanıt kütükleri kirlilik sayılmaz

`git_is_dirty()` artık `registry/experiments.jsonl` ve `registry/verdict_events.jsonl`
yollarını hariç tutar. Bu dosyalar koşunun çıktısıdır; girdisinin bütünlüğü hakkında hiçbir
şey söylemezler.

Muafiyet **yalnız** bu iki kütüğedir. Değişmiş kaynak, config, hipotez kartı veya izlenmeyen
yeni dosya hâlâ kirliliktir ve bayrağı `True` yapar.

### 2. Muafiyet gizlenmez, parametreliktir

`ignore=()` verilerek ham git davranışına dönülebilir ve test bunu açıkça kullanır. Fark
belgelenmiş bir karardır, sessiz bir yumuşatma değildir.

### 3. Rename iki yolu birden taşır

`git status` rename satırı `R  eski -> yeni` biçimindedir. Satır yalnız **her iki yol da**
muaf listedeyse atlanır; aksi hâlde kirlilik sayılır. Böylece bir kaynak dosyasını kanıt
kütüğü adına taşıyarak korumadan kaçmak mümkün olmaz.

### 4. Geçmiş koşular yeniden yorumlanmaz

S-0003, S-0004 ve S-0005 Registry satırlarındaki `git_dirty: true` değerleri **değiştirilmez**.
Append-only kütük geçmişi yeniden yazılmaz. Bu ADR o satırların nasıl okunması gerektiğini
açıklar: `true` değeri o koşularda kirli bir checkout kanıtı **değildir**, ölçüm aracının
kusurudur.

Tek istisna zaten kayıtlıdır: `E-20260810-185929-e3402e` **gerçekten** kirliydi (ölçüm
scriptleri commit edilmemişti) ve `V-20260810-190041-e3f90a` olayıyla `invalid` işaretlendi.

## Kanıt

`tests/test_provenance_dirty_flag.py` — her test kendi tek kullanımlık git deposunu `tmp_path`
içinde kurar; gerçek çalışma ağacına, `user_data/`'ya veya canlı Registry'ye dokunmaz:

- `test_clean_tree_is_not_dirty`
- `test_appending_to_the_evidence_log_is_not_dirt` — düzeltme devre dışıyken kırmızı; kusuru
  birebir üretir. Ham git davranışının hâlâ `True` dediğini de doğrular.
- `test_verdict_event_log_is_also_expected_output` — düzeltme devre dışıyken kırmızı.
- `test_modified_source_is_still_dirty`
- `test_untracked_source_file_is_still_dirty`
- `test_evidence_log_plus_modified_source_is_dirty` — muafiyet yanındaki gerçek kirliliği
  maskelemez.
- `test_renamed_source_is_dirty`

## Sonuçlar ve sınırlar

Temiz-ağaç kuralı bu ADR ile **ilk kez uygulanabilir** hâle gelir. Bundan sonraki ölçümler
gerçekten temiz bir checkout'ta koşulduğunu kanıtlayabilir.

Bu ADR performans, yön veya hipotez kabulü hakkında hiçbir şey söylemez. Geçmiş retleri
(S-0003, S-0004, S-0005) değiştirmez: o koşuların ret gerekçeleri ekonomik ve istatistikseldi,
provenance bayrağıyla ilgili değildi.
