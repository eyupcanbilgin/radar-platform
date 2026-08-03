# ADR 0003 — Point-in-time depo ve değişmez rejim snapshot'ı

- **Tarih:** 2026-08-03
- **Durum:** Kabul edildi
- **Kaynak:** CR-002 P0-1 (iki bağımsız değerlendiricinin ortak bulgusu — [ÇİFT])

## Bağlam

radar-signal, sinyal üretirken rejim skorunu btc-radar'dan alacak. "Şu anki skor"
(latest) sorgusu backtest'i sessizce yalancı yapar: bugünkü veriyle geçmişteki bir
kararı puanlamak look-ahead'dir. Ayrıca on-chain kaynaklar geçmişi revize edebilir;
"o gün ne biliyorduk" ile "bugün geçmiş için ne diyor" ayrılmazsa replay imkânsızdır.

## Karar

**1. PIT deposu (`core/store.py`) append-only'dir.** Her satır `event_time`,
`available_at`, `ingested_at`, `provider`, `schema_version`, `payload_hash` taşır.
Revizyon güncelleme değil yeni satırdır; `read_as_of(as_of)` yalnız
`available_at <= as_of` satırlarını görür ve üçlü (metrik, varlık, venue) başına en
güncel olanı seçer. Look-ahead uygulama katmanında değil **depo katmanında** imkânsızdır.

**2. `available_at` bilinmiyorsa `retrieved_at` kullanılır.** Provider yayın gecikmesini
biliyorsa (ör. funding saat sonu yayımlanır) kendisi doldurur. Bilinmiyorken çekim anını
kullanmak muhafazakâr taraftır: veriyi olduğundan daha geç bilinmiş sayarız, daha erken değil.

**3. Snapshot kimliği girdilerin deterministik türevidir.**
`snapshot_id = SNAP-sha256(as_of, feature_version, scoring_version, weights_hash,
input_digest)[:16]`. Aynı girdi → aynı id; bu sayede değişmezlik denetimi gerçek bir
koruma olur. `computed_at` (duvar saati) kimliğe ve içerik hash'ine **girmez** — yoksa
replay'de her koşu farklı çıkardı.

**4. Depo taşınan hash'e güvenmez.** `SnapshotStore.put()` içerik hash'ini gövdeden
yeniden hesaplar ve karşılaştırır. Bu, P0-1 testleri yazılırken bulunan gerçek bir açığı
kapatır: alanı elle değiştirilmiş bir kayıt önceki tasarımda "aynı içerik" sanılıp sessizce
kabul ediliyordu. İki ayrı koruma vardır:
`İÇERİK HASH UYUŞMUYOR` (kurcalanmış kayıt) ve `DEĞİŞMEZLİK İHLALİ` (aynı girdi kimliğiyle
farklı skor — sürümü yükseltilmemiş kod değişikliğinin imzası).

**5. `get_as_of` var, `get_latest` YOK.** radar-signal `as_of=<mum kapanışı>` sormak
zorundadır; API'de "latest" yüzeyi bilerek bulunmaz.

**6. Skor toplama (`core/scoring.py`) saf fonksiyondur:** I/O yok, saat yok, bileşenler
(layer, metric) adına göre sıralanarak toplanır (float toplama sırası sonucu etkiler),
çıktı 6 basamağa yuvarlanır. Replay bit-bit eşitliği bu üç kurala dayanır.

## Bilinçli kapsam sınırları

- **Metrik→d/r dönüşümü (signal_rules.yaml) bu ADR'de YOK** — Faz 1. `compute_snapshot`
  bileşen üreticisini (`component_builder`) dışarıdan alır; testler gerçekçi bir üretici
  takarak tüm yolu (depo → bileşen → toplama → snapshot → hash) zorlar.
- **§6 rejim sınıflandırma tablosu yok.** Etiket şimdilik iki değer alır: güven eşiğin
  altındaysa `veri_yetersiz`, değilse `siniflandirilmadi_faz1`.
- **CR-002 P1-1 bu modülü revize edecek** (kapsam shrinkage'ı, iki kademeli toplama,
  histerezis). P1 kendi kabul kriterleriyle ayrı iş kalemidir; yarısını burada uygulamak
  ölçümü bulanıklaştırırdı.

## Kabul testi (karşılandı)

`tests/test_snapshot.py::test_replay_determinism_100x` — 100 replay, her turda taze depo:
tek `snapshot_id`, tek `content_hash`, tek gövde (computed_at hariç). Ek olarak
`test_snapshot_excludes_data_published_after_as_of` yayın-anı kuralını uçtan uca doğrular.
