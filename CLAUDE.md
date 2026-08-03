# CLAUDE.md — btc-radar-mcp Çalışma Kuralları

Bu dosya, bu repoda çalışan Claude Code oturumları için bağlayıcıdır. İşlevsel gereksinimler için `SPEC.md` oku — kod yazmaya başlamadan önce, her oturumda.

## Proje kimliği
Bitcoin merkezli kripto piyasa analizi için FastMCP sunucusu. **Sadece okuma yapan araştırma aracı**: emir göndermez, private API key ile borsa hesabına bağlanmaz, yatırım tavsiyesi üretmez. Skorlama deterministiktir; yorum LLM'e bırakılır.

## Teknoloji seti
- Python ≥3.11, paket yönetimi **uv** (pip değil). Çalıştırma: `uv run btc-radar`, dağıtım hedefi: `uvx`.
- FastMCP (araç tanımları), httpx (async istekler), Pydantic v2 (veri sözleşmeleri), diskcache (TTL önbellek), PyYAML (config), pytest + pytest-asyncio + respx (test).
- Lint/format: ruff (`line-length = 100`). Commit öncesi `uv run ruff check --fix && uv run ruff format`.

## Dizin yapısı
```
btc_radar/
  server.py            # SADECE @app.tool tanımları + shape() + classify_tool_error()
  core/                # router, normalizer, validator, features, scoring, cache
  providers/           # kaynak başına bir dosya; hepsi BaseProvider'dan türer
  models/              # Pydantic: RawObservation, skor çıktıları, enum/Literal'lar
config/
  weights.yaml         # katman ağırlıkları — ASLA koda gömme
  signal_rules.yaml    # metrik → d/r dönüşüm kuralları
tests/
  fixtures/            # kaydedilmiş gerçek API yanıtları (anonimleştirme gerekmez, public veri)
docs/adr/              # mimari kararlar: NNNN-baslik.md
```

## Değiştirilemez kurallar
1. **SSL doğrulamasını global kapatma.** `ssl._create_unverified_context` ve `verify=False` yasak. Sertifika sorunu → kaynak bazlı çözüm + ADR.
2. **Fail-loud parse.** Sayı parse edilemiyorsa `ValueError` fırlat; asla 0 veya None'a sessizce düşme. Eksik veri "sıfır" değildir.
3. **Ağırlık ve eşikler config'den okunur.** Kodda sabit skor eşiği görürsem yanlış yazılmıştır.
4. **Araç şemaları daraltılmış Literal kullanır.** Araç, desteklemediği parametre değerini şemada ilan edemez. Yeni market/venue eklerken önce Literal'ı güncelle.
5. **Her araç yanıtı `shape()`'ten geçer** (null temizliği + kompakt markdown). Kırpma yapıldıysa `meta.truncated` + LLM'e daraltma tavsiyesi eklenir.
6. **Her exception `classify_tool_error()` üzerinden ToolError'a çevrilir** ve mesaj LLM'e "sonraki adımda ne dene" söyler. Ham stack trace LLM'e sızmaz.
7. **Zaman her yerde UTC + timezone-aware** (`datetime.now(timezone.utc)`). Naive datetime yasak. Yanıtlarda `timestamp_utc` ve `retrieved_at_utc` ayrı alanlardır.
8. **bitcoin-data.com'a önbelleksiz istek atma.** Limit 8/saat, 15/gün. Cache TTL on-chain için ≥6 saat; testlerde bu kaynak her zaman mock/fixture.
9. **Araç sayısı 8.** Dokuzuncu aracı eklemeden önce mevcut araca parametre eklemeyi değerlendir ve ADR yaz.
10. **Yatırım tavsiyesi dili yok.** "Al", "sat", "kesin yükselir" kalıpları hiçbir çıktıda, docstring'de, test verisinde yer almaz. Metodoloji §11.3 dil kuralları geçerli.

## Kodlama pratikleri
- Provider'lar `BaseProvider` ABC'sini uygular: `async fetch(metric, **params) -> list[RawObservation]`. Router ham dict taşır; Pydantic doğrulaması provider çıkışında bir kez.
- Her provider dosyasının başına kaynak URL, rate limit, bilinen tuhaflıklar yorum bloğu yazılır (borsa-mcp `parse_tcmb_number` tarzı: gelecekteki geliştiriciye ders bırak).
- Docstring'lerde her MCP aracı için ≥2 gerçek çağrı örneği.
- Log: `logging` modülü, araç girişinde parametrelerle INFO; hata durumunda `logger.exception`. `print()` yasak.
- Yeni bağımlılık eklemeden önce gerekçeyi commit mesajına yaz; `requests`, `pandas` gibi ağır bağımlılıklar için önce mevcut setle çözülemediğini göster.

## Test disiplini (Definition of Done)
Bir iş şu üçü olmadan bitmedi sayılmaz:
1. Birim/sözleşme testi yazıldı ve `uv run pytest` yeşil.
2. `uv run ruff check` temiz.
3. Davranış değişikliğiyse SPEC.md veya ADR güncellendi.

- Scoring motoru değişikliklerinde altın-değer testleri güncellenir ve determinizm testi (aynı fixture → aynı skor) korunur.
- Canlı API'ye giden test yazma; canlı doğrulama sadece `make smoke` içindir.

## Oturum akışı
1. Oturum başında: `SPEC.md` + son 3 ADR + `git log --oneline -10` oku.
2. Büyük değişiklikte önce plan yaz, onay al, sonra uygula.
3. Endpoint sözleşmesi SPEC'teki ⚠️ işaretli varsayımdan farklı çıkarsa: durup SPEC'i güncelle, ADR yaz, sonra devam et. Sessizce uyarlama yapma.
4. Bu repo tek yazarlıdır (Claude Code). Başka araçların ürettiği diff'ler doğrudan merge edilmez; inceleme girdisi olarak değerlendirilir.
