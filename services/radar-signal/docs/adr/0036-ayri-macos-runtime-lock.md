# ADR-0036 — Ayrı macOS Paper Runtime Lock

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0034, ADR-0035

## Bağlam

Tam `requirements.lock`, backtest ve araştırma için pandas, NumPy, PyArrow ve Freqtrade
yüzeyini de taşır. ADR-0035 production context loader'ını bu yüzeyden ayırdı; ancak macOS
LaunchAgent'ları için kurulabilir dar ortam hâlâ sürümlenmemişti. Ayrıca tam lock'taki bazı
gelecek sürümler mevcut macOS paket indeksinde çözülemiyordu.

## Karar

1. `requirements-runtime.lock` yalnız producer dışındaki Signal saatlik karar ve outbox pump
   süreçlerinin production bağımlılıklarını ve transitif sürümlerini sabitler.
2. Runtime lock pandas, NumPy, PyArrow ve Freqtrade içeremez. Araştırma ve test ortamı mevcut
   `requirements.lock` ile ayrı kalır.
3. Doğrudan production paketleri ccxt, httpx, jsonschema, pydantic ve PyYAML'dır. Sürümler
   CPython 3.12/macOS arm64 için sabitlenir; tam lock ile sürüm eşitliği varsayılmaz.
   Python 3.14, ccxt'nin zorunlu coincurve bağımlılığı hazır wheel sağlamadığı için desteklenmez.
4. CI temiz bir macOS/Python 3.12 venv'ine runtime lock'ı kurar ve production entrypoint
   import smoke'unu çalıştırır. Smoke araştırma paketlerinden birini görürse fail-closed olur.
5. Ayrı lock karar, eşik, forward gözlem veya delivery davranışını değiştirmez; gerçek emir,
   private API, forward backfill ve `direction` üretimi kapalı kalır.

## Sonuç

LaunchAgent'lar araştırma ortamından bağımsız, tekrar kurulabilir küçük bir Signal Python
ortamına işaret edebilir. Lock güncellemesi production import smoke ve bağımsız PR incelemesi
olmadan kabul edilmez.
