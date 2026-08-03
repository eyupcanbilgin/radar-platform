"""Ölçüm geçerliliği modülü (ADIM 2).

1. Sermaye tükenmesi (bankruptcy/depletion) kontrolü.
2. İşlem başına brüt/net beklenti (expectancy in % and bps) hesaplama.
"""

from datetime import datetime


def check_capital_depletion(
    last_trade_date: str | datetime | None,
    timerange_end: str | datetime | None,
    final_balance: float,
    starting_balance: float = 10000.0,
    threshold_days: float = 7.0,
    underwater_threshold_pct: float = 85.0,
) -> tuple[bool, str]:
    """Sermaye tükenmesi kontrolü.

    Son işlem tarihi dönemin sonundan threshold_days gün öncesiyse VE bakiye
    %underwater_threshold_pct düşmüşse: (True, "GEÇERSİZ — sermaye tükendi") döndürür.
    """
    loss_pct = (starting_balance - final_balance) / starting_balance * 100.0
    if loss_pct >= underwater_threshold_pct:
        if last_trade_date and timerange_end:
            if isinstance(last_trade_date, str):
                last_dt = datetime.fromisoformat(last_trade_date.replace("Z", "+00:00"))
            else:
                last_dt = last_trade_date
            if isinstance(timerange_end, str):
                end_dt = datetime.fromisoformat(timerange_end.replace("Z", "+00:00"))
            else:
                end_dt = timerange_end

            diff_days = (end_dt - last_dt).total_seconds() / 86400.0
            if diff_days >= threshold_days:
                return (
                    True,
                    f"GEÇERSİZ — sermaye tükendi (son işlem dönem sonundan {diff_days:.1f} gün önce; kayıp %{loss_pct:.1f})",
                )
    return False, "OK"


def calculate_expectancy(trades: list[dict]) -> dict:
    """İşlem başına ortalama brüt ve net beklenti (expectancy)."""
    if not trades:
        return {"count": 0, "net_expectancy_pct": 0.0, "net_expectancy_bps": 0.0}

    total_profit_pct = sum(t.get("profit_ratio", 0.0) for t in trades)
    count = len(trades)
    avg_profit_pct = (total_profit_pct / count) * 100.0
    avg_profit_bps = avg_profit_pct * 100.0

    return {
        "count": count,
        "net_expectancy_pct": round(avg_profit_pct, 4),
        "net_expectancy_bps": round(avg_profit_bps, 2),
    }
