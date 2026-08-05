.PHONY: test lint download-data download-coinbase-spot manifest verify backtest lookahead pulse-smoke pulse-reanalysis hourly-once hourly-daemon

PY=.venv/Scripts/python
FT=.venv/Scripts/freqtrade

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check && $(PY) -m ruff format --check

download-data:
	$(FT) download-data --exchange binance --trading-mode futures \
	  --pairs BTC/USDT:USDT ETH/USDT:USDT -t 15m 1h --timerange 20190908- --userdir user_data

download-coinbase-spot:
	$(PY) scripts/download_coinbase_spot.py --end 2026-08-04T00:00:00Z

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

pulse-smoke:
	$(PY) scripts/run_pulse_reanalysis.py --allow-dirty-smoke --permutations 50 \
	  --out var/pulse-v2-smoke.json

pulse-reanalysis:
	$(PY) scripts/run_pulse_reanalysis.py

hourly-once:
	$(PY) scripts/run_hourly_decision.py

hourly-daemon:
	$(PY) scripts/run_hourly_decision.py --daemon
