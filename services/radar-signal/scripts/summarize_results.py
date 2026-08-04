import json
from pathlib import Path

path = Path("services/radar-signal/docs/reviews/2026-08-04-eleme/eleme-sonuclari.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

tests = data["tests"]
print(f"Total registered tests executed: {len(tests)}")

cards = {}
for t in tests:
    c = t["card"]
    if c not in cards:
        cards[c] = []
    cards[c].append(t)

for card, tlist in cards.items():
    print(f"\n=======================================================")
    print(f"KART {card} ({len(tlist)} test)")
    print(f"=======================================================")
    dir_candidates = [t for t in tlist if t["mode"] == "directional" and t["beats_cost"] and t["sig_fdr_05"]]
    vol_candidates = [t for t in tlist if t["mode"] == "volatility_ratio" and t["mean_bps"] > 0 and t["sig_fdr_05"]]
    print(f"  Yönsel maliyet aşımı ve FDR p<=0.05: {len(dir_candidates)}")
    print(f"  Volatilite genişlemesi ve FDR p<=0.05: {len(vol_candidates)}")
    
    for t in tlist:
        p_fdr_str = f"{t['p_fdr']:.4f}" if not str(t['p_fdr']).startswith("nan") else "NaN"
        print(f"  {t['symbol']:>3} | {t['variant']:<32} | {t['horizon']:>5} | {t['mode']:<16} | n={t['n_signals']:<5} | mean={t['mean_bps']:>7.2f} | hit={t['hit_rate']:>5.1%} | p_raw={t['p_raw']:>6.4f} | p_fdr={p_fdr_str:>6} | beats={str(t['beats_cost']):>5}")
