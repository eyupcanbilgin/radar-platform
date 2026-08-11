.PHONY: test lint smoke smoke-evidence

test:
	uv run pytest

lint:
	uv run ruff check && uv run ruff format --check

smoke:
	uv run python scripts/verify_endpoints.py

# Binance/Bybit zincirinin TEK kanıt kaynağı. Günlük CI koşusu coğrafi olarak engelli bir
# bölgeden çalışır ve o uçlar için kanıt üretmez (ADR-0009); yeşil rozet onları kapsamaz.
# Bu hedef engellenmemiş bir ağdan çalıştırılmalıdır: engel varsa çıkış kodu 2 olur ve
# kütüğe hiçbir şey yazılmaz (ADR-0013).
smoke-evidence:
	uv run python scripts/verify_endpoints.py --fail-on-blocked \
	  --record docs/endpoint-verification-log.md
