<!-- Kaynak: ChatGPT maliyet araştırması · Alınma: 3 Ağustos 2026 · CR-001/CR-5'in kanıt kaynağı -->

**Binance USDT-M (USDⓈ-M) gerçekçi maliyet parametreleri (VIP0 / Regular User, Ağustos 2026 itibarıyla):**

### 1. Komisyon Oranları (Maker / Taker)

Resmi tabloya göre:

| Durum                  | Maker     | Taker     |
|------------------------|-----------|-----------|
| **BNB indirimsiz**     | 0.0200%   | 0.0500%   |
| **BNB %10 indirimli**  | 0.0180%   | 0.0450%   |

- BNB indirimi sadece Futures cüzdanında yeterli BNB varsa ve ücret BNB ile ödendiğinde uygulanır (spot'taki %25 değil, futures'ta sabit %10).
- VIP0 eşiği: 30 günlük işlem hacmi < 5M USD (veya BNB bakiyesi 0).

**Backtest önerisi:**
- Taker ağırlıklı strateji → **0.045%** (BNB'li) veya muhafazakâr **0.05%**.
- Maker + limit order karışımı varsa weighted average kullan (ör. %60 taker / %40 maker → ~0.036–0.038% civarı).
- Round-trip (aç + kapa) için 2× uygula.

### 2. Slippage (15m bar, BTCUSDT & ETHUSDT)

Her iki çift de çok likit. 15m barlarda makul pozisyon büyüklükleri (retail / küçük-orta institutional) için:

**Önerilen varsayımlar (one-way, market order):**

| Çift       | Gerçekçi (iyi likidite) | Muhafazakâr / Stres | Açıklama |
|------------|--------------------------|---------------------|----------|
| **BTCUSDT** | 0.01% – 0.02%           | 0.03% – 0.05%      | Spread genellikle ≤ 0.01%. Impact düşük. |
| **ETHUSDT** | 0.015% – 0.025%         | 0.04% – 0.06%      | BTC'ye göre biraz daha geniş. |

- 15m bar kullanıyorsan high/low veya open'a göre fill modellemek yerine sabit bps + küçük rastgele noise eklemek daha stabil sonuç verir.
- Çok agresif market order + büyük size varsayımı yoksa **BTC 0.02% / ETH 0.025%** one-way iyi bir başlangıç noktasıdır.
- Round-trip slippage = 2× one-way.

### 3. Funding Maliyeti (Intraday, birkaç saat açık pozisyon)

**Nasıl çalışır:**
- Funding **sadece** settlement anında (varsayılan: 00:00, 08:00, 16:00 UTC) pozisyon açıksa uygulanır.
- Pro-rata yok. Settlement'tan 1 saniye önce kapatırsan o interval için 0 ödersin/alırsın.
- Formül: `Funding Payment = Position Notional × Funding Rate`
- Pozitif rate → Long'lar Short'lara öder. Negatif → tersi.
- Base interest component ≈ **0.01% / 8 saat** (0.03%/gün). Gerçek rate premium'a göre değişir.

**Intraday (birkaç saat) için pratik yaklaşımlar:**

1. **En doğru (önerilen):** Timestamp bazlı simülasyon
   Pozisyon funding zamanına denk geliyorsa o anki rate'i uygula, gelmiyorsa 0.

2. **Basit config için (beklenen değer):**
   Ortalama hold süresi `H` saat ise yaklaşık maliyet:
   ```
   Expected Funding ≈ (H / 8) × Average_Rate
   ```
   - Tipik Average_Rate (nötr/orta vadeli): **+0.005% ~ +0.015%** / 8h (çoğu zaman 0.01% civarı dolaşır).
   - Bull piyasada long'lar için daha yüksek (0.02–0.05%+), bear'da negatif olabilir.

3. **Muhafazakâr backtest varsayımı:**
   - Her trade'e sabit **0.005% – 0.01%** funding maliyeti ekle (hold süresi 2–6 saat varsayımıyla).
   - Veya yön bağımsız olarak "funding drag" olarak 0.008%/trade kullan.

**Not:** Funding ücreti Binance tarafından alınmaz, long/short arasında transfer edilir. Backtest'te long bias'lı stratejilerde pozitif rate dönemlerinde ekstra maliyet, short bias'lılarda fırsat olarak çıkar.

### Backtest Config Özeti (VIP0, BNB'li, 15m)

```text
taker_fee          = 0.00045   # 0.045%
maker_fee          = 0.00018   # 0.018%
slippage_btc       = 0.00020   # 0.02% one-way
slippage_eth       = 0.00025   # 0.025% one-way
funding_per_8h     = 0.00010   # 0.01% baseline (veya historical series kullan)
# veya fixed funding cost per trade ≈ 0.00005 – 0.00010
```

Bu sayılar "gerçekçi ama biraz muhafazakâr" tarafta. Daha agresif (daha düşük maliyet) varsayımlarla da çalıştırıp sonuçları karşılaştırabilirsin. Faz A raporu geldiğinde özellikle funding rate serisi ve gerçek fill'lerin kayma dağılımı ile çapraz kontrol etmek en sağlıklısı olur.
