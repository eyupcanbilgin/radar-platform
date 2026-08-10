"""Execute the same pre-registered signal on a second venue, so the venue gate can run.

The hypothesis cards make venue robustness an acceptance criterion, but with a single
execution venue `evaluate_period_venue_fragility` could never be evaluated: S-0005 and
S-0006 both had to report it `not_evaluated`.  A criterion that can never be evaluated is
not a criterion — it is decoration.

What this measures is a real question, not a formality: **would the same rule have made
money somewhere else?**  An edge that exists only on the venue it was fitted to is a venue
artifact (fee schedule, liquidity, listing history), not a market effect.

What it deliberately does NOT do:

- It does not re-derive the signal from the second venue's prices.  The signal stays exactly
  as pre-registered; only the *execution* prices change.  Recomputing the signal per venue
  would silently create a second hypothesis.
- It does not fill missing hours.  A venue that lacks an hour simply produces no trade for
  it; the hour is dropped, never imputed.
"""

import pandas as pd

from scripts.evaluate_s0005 import _collect_trades


def load_venue_price_frame(path, *, prefix: str = "perp") -> pd.DataFrame:
    """Bir mekânın 1h OHLCV'sini `_collect_trades`'in beklediği kolon adlarına çevir."""
    frame = pd.read_feather(path)
    frame["date_dt"] = pd.to_datetime(frame["date"], utc=True)
    return frame[["date_dt", "open", "close"]].rename(
        columns={"open": f"{prefix}_open", "close": f"{prefix}_close"}
    )


def collect_venue_returns(
    *,
    signals_frame: pd.DataFrame,
    venue_frames: dict[str, pd.DataFrame],
    plan: dict,
    fee: dict[str, float],
) -> dict[str, dict[str, list[float]]]:
    """Aynı sinyalleri her mekânın fiyatlarıyla işle; mekân → senaryo → getiriler.

    ``signals_frame`` ön-kayıtlı sinyali taşır ve DEĞİŞMEZ; her mekân için yalnız
    ``perp_open``/``perp_close`` kolonları o mekânın fiyatlarıyla değiştirilir.
    """
    if not venue_frames:
        raise ValueError("en az bir mekân gerekli")

    signal_columns = ["date_dt", "signal"]
    missing = [column for column in signal_columns if column not in signals_frame.columns]
    if missing:
        raise ValueError(f"sinyal çerçevesinde eksik kolon: {missing}")

    results: dict[str, dict[str, list[float]]] = {}
    for venue, prices in venue_frames.items():
        merged = signals_frame[signal_columns].merge(prices, on="date_dt", how="inner")
        merged = merged.sort_values("date_dt").reset_index(drop=True)
        if merged.empty:
            # Sessizce boş geçmek "bu mekânda sonuç yoktu" gibi okunurdu; fail-loud.
            raise ValueError(f"{venue}: sinyal ve fiyat serileri hiç kesişmiyor")
        trades = _collect_trades(merged, plan, fee)
        results[venue] = trades["net_by_scenario"]
    return results
