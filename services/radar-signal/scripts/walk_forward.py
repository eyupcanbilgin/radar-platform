"""Purged Walk-Forward + Embargo CLI Komut Satırı Aracı.

Kullanım:
  python scripts/walk_forward.py generate-plan --start 2024-01-01 --end 2024-06-01
  python scripts/walk_forward.py validate-plan --plan-file plan.json
  python scripts/walk_forward.py evaluate-windows --plan-file plan.json --data-file data.csv

İşlevsellik:
  - Strateji veya yön üretmez.
  - Sadece split planı ve ölçüm iskeleti sunar.
  - Locked OOS varsayılan olarak kilitlidir ve CLI açamaz.
  - Eksik/boş veri durumunda sıfır getiri üretmez; fail-closed `unavailable`/`invalid` döner.
"""

import argparse
import json
import sys
from pathlib import Path

from scripts.walk_forward_lib import (
    LockedOOSAccessError,
    ProtocolValidationError,
    evaluate_window_data,
    generate_walk_forward_plan,
    load_research_protocol_config,
    validate_split_plan,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Purged Walk-Forward + Embargo CLI Araci (Phase 2 Protocol)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. generate-plan
    gen_parser = subparsers.add_parser("generate-plan", help="Split plani JSON uretir.")
    gen_parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01T00:00:00Z",
        help="Baslangic tarihi (UTC ISO)",
    )
    gen_parser.add_argument(
        "--end",
        type=str,
        default="2024-06-01T00:00:00Z",
        help="Bitis tarihi (UTC ISO)",
    )
    gen_parser.add_argument(
        "--horizon-hours",
        type=int,
        default=24,
        help="Label forward horizon saati",
    )
    gen_parser.add_argument(
        "--embargo-days",
        type=int,
        default=1,
        help="Embargo gun sayisi (min 1)",
    )
    gen_parser.add_argument(
        "--train-days",
        type=int,
        default=90,
        help="Train penceresi gun sayisi",
    )
    gen_parser.add_argument(
        "--test-days",
        type=int,
        default=30,
        help="Test penceresi gun sayisi",
    )
    gen_parser.add_argument(
        "--step-days",
        type=int,
        default=30,
        help="Adim kaydirma gun sayisi",
    )
    gen_parser.add_argument(
        "--allow-locked-oos",
        action="store_true",
        default=False,
        help="Locked OOS donemini acma bayragi (varsayilan: False)",
    )
    gen_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Özel research_protocol.yaml yolu",
    )

    # 2. validate-plan
    val_parser = subparsers.add_parser("validate-plan", help="Plan JSON'ini dogrular.")
    val_parser.add_argument(
        "--plan-file",
        type=Path,
        default=None,
        help="Plan JSON dosyasi yolu (stdin icin bos birakin)",
    )
    val_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Özel research_protocol.yaml yolu",
    )

    # 3. evaluate-windows
    eval_parser = subparsers.add_parser("evaluate-windows", help="Pencere verisini degerlendirir.")
    eval_parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="Plan JSON dosyasi yolu",
    )
    eval_parser.add_argument(
        "--data-file",
        type=Path,
        default=None,
        help="Mum verisi dosyasi yolu (yoksa fail-closed unavailable döner)",
    )
    eval_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Özel research_protocol.yaml yolu",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        cfg = load_research_protocol_config(args.config)

        if args.command == "generate-plan":
            plan = generate_walk_forward_plan(
                start_time=args.start,
                end_time=args.end,
                horizon_hours=args.horizon_hours,
                embargo_days=args.embargo_days,
                train_window_days=args.train_days,
                test_window_days=args.test_days,
                step_days=args.step_days,
                allow_locked_oos=args.allow_locked_oos,
                config=cfg,
            )
            # Verify generated plan before printing
            validate_split_plan(plan, config=cfg)
            print(json.dumps(plan, indent=2))

        elif args.command == "validate-plan":
            if args.plan_file:
                content = args.plan_file.read_text(encoding="utf-8")
            else:
                content = sys.stdin.read()
            plan = json.loads(content)
            validate_split_plan(plan, config=cfg)
            print(json.dumps({"status": "ok", "valid": True}, indent=2))

        elif args.command == "evaluate-windows":
            content = args.plan_file.read_text(encoding="utf-8")
            plan = json.loads(content)

            candles = None
            if args.data_file and args.data_file.exists():
                try:
                    candles = json.loads(args.data_file.read_text(encoding="utf-8"))
                except Exception:
                    candles = None

            evaluated_folds = []
            for fold in plan.get("folds", []):
                ev = evaluate_window_data(fold, candles, config=cfg)
                evaluated_folds.append(ev)

            plan["folds"] = evaluated_folds
            print(json.dumps(plan, indent=2))

    except (LockedOOSAccessError, ProtocolValidationError) as err:
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
