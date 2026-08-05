"""Faz 2 Referans Taban Çizgisi (Baseline) Değerlendiricisi.

Bu modül, Purged Walk-Forward fold planını ve mum verilerini girdi alarak 3 referans
taban çizgisini (cash, buy_and_hold, simple_trend) maliyet SONRASI ölçer.

İlkeler:
1. Alpha iddiası değildir; stratejilerin aşması gereken referans taban çizgileridir.
2. Tüm getiriler config/costs.yaml matrisindeki senaryolara (varsayılan: realistic)
   göre maliyet sonrası (komisyon + kayma) hesaplanır. Maliyetsiz getiri üretilmez.
3. Eşikler ve parametreler config'den gelir; Python kodunda sabit sayı kullanılamaz.
4. Locked OOS dönemi varsayılan olarak kilitlidir ve CLI ile açılamaz (ADR-0014 mirası).
5. Boş, eksik veya gap içeren verilerde 0/nötr getiri uydurulmaz; `unavailable` veya
   `invalid` döner.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.costslib import effective_fee, load_costs
from scripts.walk_forward_lib import (
    LockedOOSAccessError,
    ProtocolValidationError,
    evaluate_window_data,
    load_research_protocol_config,
    parse_utc_datetime,
    validate_split_plan,
)


def _filter_candles_in_range(
    candles: list[dict], start_dt: datetime, end_dt: datetime
) -> list[dict]:
    """Mum listesini [start_dt, end_dt) aralığına göre filtreler ve zamana göre sıralar."""
    res = []
    for c in candles:
        ts_val = c.get("timestamp") or c.get("date") or c.get("time")
        if ts_val is None:
            continue
        if isinstance(ts_val, (int, float)):
            cur_dt = datetime.fromtimestamp(ts_val / 1000.0 if ts_val > 2e9 else ts_val, tz=UTC)
        else:
            cur_dt = parse_utc_datetime(ts_val)

        if start_dt <= cur_dt < end_dt:
            res.append((cur_dt, c))

    res.sort(key=lambda x: x[0])
    return [item[1] for item in res]


def _calculate_max_drawdown(equity_curve: list[float]) -> float:
    """Sermaye eğrisi üzerinden maksimum göreli düşüşü (max drawdown) hesaplar."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def evaluate_baseline_cash(fold: dict, candles: list[dict] | None, window_valid: bool) -> dict:
    """(1) Cash / İşlem Yok Taban Çizgisi.

    Hiç pozisyon alınmaz. Net getiri = 0.0. Fırsat maliyeti / piyasa hareketi kaydedilir.
    """
    if not window_valid or not candles:
        return {
            "baseline_name": "cash",
            "status": fold.get("status", "unavailable"),
            "reason": fold.get("reason", "no_data"),
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
            "opportunity_return": None,
        }

    first_open = float(candles[0].get("open", candles[0].get("close", 0.0)))
    last_close = float(candles[-1].get("close", 0.0))

    opp_return = (last_close - first_open) / first_open if first_open > 0 else 0.0

    return {
        "baseline_name": "cash",
        "status": "evaluated",
        "trade_count": 0,
        "raw_return": 0.0,
        "net_return": 0.0,
        "max_drawdown": 0.0,
        "opportunity_return": opp_return,
    }


def evaluate_baseline_buy_and_hold(
    fold: dict,
    candles: list[dict] | None,
    costs: dict,
    scenario: str,
    window_valid: bool,
) -> dict:
    """(2) Buy & Hold Taban Çizgisi.

    Test penceresi başında alıp sonunda satma. Giriş ve çıkış komisyonu + kayma düşülür.
    """
    if not window_valid or not candles:
        return {
            "baseline_name": "buy_and_hold",
            "status": fold.get("status", "unavailable"),
            "reason": fold.get("reason", "no_data"),
            "cost_scenario": scenario,
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
        }

    first_open = float(candles[0].get("open", candles[0].get("close", 0.0)))
    last_close = float(candles[-1].get("close", 0.0))

    if first_open <= 0 or last_close <= 0:
        return {
            "baseline_name": "buy_and_hold",
            "status": "invalid",
            "reason": "invalid_prices",
            "cost_scenario": scenario,
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
        }

    fee_oneside = effective_fee(costs, scenario)

    # Entry with fee & slippage, exit with fee & slippage
    raw_return = (last_close - first_open) / first_open

    # Net return multiplicative: (1 + raw_return) * (1 - fee) / (1 + fee) - 1
    net_return = (1.0 + raw_return) * (1.0 - fee_oneside) / (1.0 + fee_oneside) - 1.0

    # Calculate equity curve & max drawdown in test window
    equity_curve = [first_open * (1.0 + fee_oneside)]
    for c in candles:
        c_close = float(c.get("close", first_open))
        c_high = float(c.get("high", c_close))
        c_low = float(c.get("low", c_close))
        equity_curve.append(c_high)
        equity_curve.append(c_low)
        equity_curve.append(c_close)

    max_dd = _calculate_max_drawdown(equity_curve)

    return {
        "baseline_name": "buy_and_hold",
        "status": "evaluated",
        "cost_scenario": scenario,
        "effective_fee_oneside": fee_oneside,
        "trade_count": 1,
        "raw_return": raw_return,
        "net_return": net_return,
        "max_drawdown": max_dd,
        "reference_price": first_open,
        "close_price": last_close,
    }


def evaluate_baseline_simple_trend(
    fold: dict,
    test_candles: list[dict] | None,
    all_candles: list[dict] | None,
    costs: dict,
    scenario: str,
    trend_cfg: dict,
    window_valid: bool,
) -> dict:
    """(3) Basit Trend Kontrolü (MA Crossover) Taban Çizgisi.

    Parametreler config/research_protocol.yaml içinden gelir (fast_period, slow_period).
    İşlem başına komisyon + kayma düşülür.
    """
    fast_period = int(trend_cfg.get("fast_period", 20))
    slow_period = int(trend_cfg.get("slow_period", 50))
    signal_mode = trend_cfg.get("signal_mode", "long_short")

    if not window_valid or not test_candles or not all_candles:
        return {
            "baseline_name": "simple_trend",
            "status": fold.get("status", "unavailable"),
            "reason": fold.get("reason", "no_data"),
            "cost_scenario": scenario,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
        }

    fee_oneside = effective_fee(costs, scenario)

    # Compute Moving Averages using all_candles (including train warmup)
    closes = [float(c.get("close", 0.0)) for c in all_candles]
    if len(closes) < slow_period:
        return {
            "baseline_name": "simple_trend",
            "status": "invalid",
            "reason": f"insufficient_warmup_candles:{len(closes)}<{slow_period}",
            "cost_scenario": scenario,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
        }

    sma_fast = []
    sma_slow = []
    for i in range(len(closes)):
        if i >= fast_period - 1:
            sma_fast.append(sum(closes[i - fast_period + 1 : i + 1]) / fast_period)
        else:
            sma_fast.append(None)

        if i >= slow_period - 1:
            sma_slow.append(sum(closes[i - slow_period + 1 : i + 1]) / slow_period)
        else:
            sma_slow.append(None)

    # Identify indices corresponding to test_candles
    test_start_dt = parse_utc_datetime(fold["test_start_utc"])
    test_end_dt = parse_utc_datetime(fold["test_end_utc"])

    test_indices = []
    for idx, c in enumerate(all_candles):
        ts_val = c.get("timestamp") or c.get("date") or c.get("time")
        if ts_val is None:
            continue
        cur_dt = (
            datetime.fromtimestamp(
                ts_val / 1000.0 if isinstance(ts_val, (int, float)) and ts_val > 2e9 else ts_val,
                tz=UTC,
            )
            if isinstance(ts_val, (int, float))
            else parse_utc_datetime(ts_val)
        )
        if test_start_dt <= cur_dt < test_end_dt:
            test_indices.append(idx)

    if not test_indices:
        return {
            "baseline_name": "simple_trend",
            "status": "unavailable",
            "reason": "test_window_candles_missing",
            "cost_scenario": scenario,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "trade_count": 0,
            "raw_return": None,
            "net_return": None,
            "max_drawdown": None,
        }

    # Simulate trading in test window
    current_pos = 0  # 0: flat, +1: long, -1: short
    trade_count = 0
    equity = 1.0
    raw_equity = 1.0
    equity_curve = [equity]

    for i_idx in test_indices:
        f_ma = sma_fast[i_idx]
        s_ma = sma_slow[i_idx]

        if f_ma is None or s_ma is None:
            desired_pos = 0
        elif f_ma > s_ma:
            desired_pos = 1
        elif f_ma < s_ma:
            desired_pos = -1 if signal_mode == "long_short" else 0
        else:
            desired_pos = current_pos

        # Price return of candle
        c_open = float(all_candles[i_idx].get("open", all_candles[i_idx]["close"]))
        c_close = float(all_candles[i_idx]["close"])
        bar_return = (c_close - c_open) / c_open if c_open > 0 else 0.0

        if desired_pos != current_pos:
            # Position change incurs fee
            trade_count += 1
            equity *= 1.0 - fee_oneside
            current_pos = desired_pos

        if current_pos != 0:
            bar_pnl = bar_return if current_pos == 1 else -bar_return
            equity *= 1.0 + bar_pnl
            raw_equity *= 1.0 + bar_pnl

        equity_curve.append(equity)

    # Close open position at end of window if active
    if current_pos != 0:
        equity *= 1.0 - fee_oneside
        trade_count += 1
        equity_curve.append(equity)

    net_return = equity - 1.0
    raw_return = raw_equity - 1.0
    max_dd = _calculate_max_drawdown(equity_curve)

    return {
        "baseline_name": "simple_trend",
        "status": "evaluated",
        "cost_scenario": scenario,
        "effective_fee_oneside": fee_oneside,
        "fast_period": fast_period,
        "slow_period": slow_period,
        "trade_count": trade_count,
        "raw_return": raw_return,
        "net_return": net_return,
        "max_drawdown": max_dd,
    }


def evaluate_fold_baselines(
    fold: dict,
    candles: list[dict] | None = None,
    costs: dict | None = None,
    protocol_cfg: dict | None = None,
    scenario: str | None = None,
) -> dict:
    """Tek bir fold için 3 referans taban çizgisini hesaplar."""
    cfg = protocol_cfg or load_research_protocol_config()
    cost_cfg = costs or load_costs()
    scen = scenario or cfg.get("baselines", {}).get("cost_scenario", "realistic")
    trend_cfg = cfg.get("baselines", {}).get(
        "simple_trend", {"fast_period": 20, "slow_period": 50, "signal_mode": "long_short"}
    )

    # Inherit Locked OOS check from walk_forward_lib
    locked_start_dt = cfg["boundaries"]["locked_oos_start_dt"]
    te_end_dt = parse_utc_datetime(fold["test_end_utc"])
    allow_locked_oos = fold.get("allow_locked_oos", False)

    if te_end_dt > locked_start_dt and not allow_locked_oos:
        raise LockedOOSAccessError(
            f"Fold #{fold.get('fold_index')} test bitişi ({te_end_dt.isoformat()}), "
            f"locked OOS sınırını ({locked_start_dt.isoformat()}) aşıyor."
        )

    # Check window data health
    val_res = evaluate_window_data(fold, candles, config=cfg)
    is_valid = val_res.get("status") == "valid"

    test_start_dt = parse_utc_datetime(fold["test_start_utc"])
    test_end_dt = parse_utc_datetime(fold["test_end_utc"])
    train_start_dt = parse_utc_datetime(fold["train_start_utc"])

    test_candles = (
        _filter_candles_in_range(candles, test_start_dt, test_end_dt) if candles else None
    )
    all_candles = (
        _filter_candles_in_range(candles, train_start_dt, test_end_dt) if candles else None
    )

    cash_res = evaluate_baseline_cash(val_res, test_candles, is_valid)
    bnh_res = evaluate_baseline_buy_and_hold(val_res, test_candles, cost_cfg, scen, is_valid)
    trend_res = evaluate_baseline_simple_trend(
        val_res, test_candles, all_candles, cost_cfg, scen, trend_cfg, is_valid
    )

    return {
        "fold_index": fold.get("fold_index"),
        "train_start_utc": fold.get("train_start_utc"),
        "test_start_utc": fold.get("test_start_utc"),
        "test_end_utc": fold.get("test_end_utc"),
        "data_status": val_res.get("status"),
        "data_reason": val_res.get("reason"),
        "baselines": {
            "cash": cash_res,
            "buy_and_hold": bnh_res,
            "simple_trend": trend_res,
        },
    }


def evaluate_plan_baselines(
    plan: dict,
    candles: list[dict] | None = None,
    costs: dict | None = None,
    protocol_cfg: dict | None = None,
    scenario: str | None = None,
) -> dict:
    """Bütün split planı için referans taban çizgilerini hesaplar."""
    cfg = protocol_cfg or load_research_protocol_config()
    cost_cfg = costs or load_costs()
    validate_split_plan(plan, config=cfg)

    evaluated_folds = []
    for fold in plan.get("folds", []):
        # Pass allow_locked_oos parameter from plan
        fold_params = dict(fold)
        fold_params["allow_locked_oos"] = plan.get("parameters", {}).get("allow_locked_oos", False)
        res = evaluate_fold_baselines(
            fold_params,
            candles=candles,
            costs=cost_cfg,
            protocol_cfg=cfg,
            scenario=scenario,
        )
        evaluated_folds.append(res)

    return {
        "protocol_version": cfg["version"],
        "plan_parameters": plan.get("parameters", {}),
        "cost_scenario": scenario or cfg.get("baselines", {}).get("cost_scenario", "realistic"),
        "evaluated_folds": evaluated_folds,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Faz 2 Referans Taban Cizgisi (Baseline) Degerlendiricisi"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Plan icin baseline getirilerini hesaplar.")
    run_parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="walk_forward.py tarafindan uretilmis plan JSON dosyasi",
    )
    run_parser.add_argument(
        "--data-file",
        type=Path,
        default=None,
        help="Mum verisi JSON/CSV dosyasi (yoksa fail-closed unavailable döner)",
    )
    run_parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Maliyet senaryosu (realistic, taker_heavy vb.)",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Ozel research_protocol.yaml yolu",
    )
    run_parser.add_argument(
        "--costs-config",
        type=Path,
        default=None,
        help="Ozel costs.yaml yolu",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        cfg = load_research_protocol_config(args.config)
        cost_cfg = load_costs(args.costs_config)

        if args.command == "run":
            content = args.plan_file.read_text(encoding="utf-8")
            plan = json.loads(content)

            candles = None
            if args.data_file and args.data_file.exists():
                try:
                    candles = json.loads(args.data_file.read_text(encoding="utf-8"))
                except Exception:
                    candles = None

            res = evaluate_plan_baselines(
                plan=plan,
                candles=candles,
                costs=cost_cfg,
                protocol_cfg=cfg,
                scenario=args.scenario,
            )
            print(json.dumps(res, indent=2))

    except (LockedOOSAccessError, ProtocolValidationError, ValueError) as err:
        print(json.dumps({"status": "error", "message": str(err)}, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(
            json.dumps({"status": "error", "message": f"Beklenmeyen hata: {err}"}, indent=2),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
