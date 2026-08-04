.PHONY: test lint download-data manifest verify backtest lookahead

PY=.venv/Scripts/python
FT=.venv/Scripts/freqtrade

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check && $(PY) -m ruff format --check

download-data:
	$(FT) download-data --exchange binance --trading-mode futures \
	  --pairs BTC/USDT:USDT ETH/USDT:USDT -t 15m 1h --timerange 20190908- --userdir user_data

manifest:
	$(PY) scripts/data_manifest.py

# Ortam sağlığı: registry encoding + manifest↔veri eşleşmesi (CI ile aynı kontroller)
verify:
	$(PY) scripts/repair_registry_encoding.py --check
	$(PY) scripts/data_manifest.py --verify

# Backtest YALNIZ bt.py sarmalayıcısıyla koşulur (maliyet + registry zorunlu; CLAUDE.md kural 6/8)
backtest:
	$(PY) scripts/bt.py --strategy $(S) --scenario realistic

lookahead:
	$(FT) lookahead-analysis --userdir user_data --config config/config.dryrun.json \
	  --strategy $(S) --timerange $(TR)
