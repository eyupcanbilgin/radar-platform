# ADR-0038 — Launchd Venv Executable Yolunu Koruma

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0034, ADR-0036, ADR-0037

## Bağlam

İlk gerçek macOS kurulumunda dört LaunchAgent da import aşamasında eksik paketle düştü.
Bağımlılıklar venv'lerde kurulu ve smoke yeşildi; ancak renderer executable yoluna
`Path.resolve()` uygulayarak `venv/bin/python` symlink'ini Homebrew ana interpreter yoluna
çeviriyordu. Launchd bu nedenle venv `sys.prefix` ve site-packages alanını kullanmıyordu.

## Karar

1. Executable doğrulaması kullanıcı yolunu absolute/normalize eder fakat symlink'i çözmez.
   Dosya ve executable izin kapıları aynı kalır.
2. Üretilen plist `ProgramArguments[0]` alanında açık venv Python yolunu taşır. MCP ve Signal
   venv'leri ayrı kalır.
3. Sentetik macOS testi venv symlink'inin korunduğunu doğrular. Windows CI'da symlink oluşturma
   izni garanti olmadığı için bu tek platform testi Windows'ta skip edilir.
4. Bu düzeltme karar, coverage, delivery veya forward semantiğini değiştirmez; emir/private
   API, geçmiş backfill ve `direction` üretimi kapalıdır.

## Sonuç

LaunchAgent süreçleri smoke ile doğrulanmış bağımlılık ortamını gerçekten kullanır. İlk hatalı
kurulumdaki süreçler durdurulmuş, state ve append-only ledger'lar korunmuştur.
