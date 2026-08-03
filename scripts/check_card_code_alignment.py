"""Kart ↔ Kod Uyum Denetimi Scripti (ADIM 3).

Bu script, strateji kodlarının (.py) ilgili hipotez kartındaki (.md) bağlayıcı kurallara
(örneğin process_only_new_candles, fixed stop vs trailing stop, enter_tag varlığı)
harfiyen uyup uymadığını otomatik denetler.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def check_alignment(strategy_file: Path, card_file: Path) -> list[str]:
    errors = []
    py_code = strategy_file.read_text(encoding="utf-8")

    # 1. process_only_new_candles kontrolü
    if "process_only_new_candles = True" not in py_code:
        errors.append(f"{strategy_file.name}: process_only_new_candles = True eksik!")

    # 2. enter_tag kontrolü
    if "enter_tag" not in py_code:
        errors.append(f"{strategy_file.name}: enter_tag tanımlaması eksik!")

    # 3. Trailing vs Sabit Stop kontrolü (S0002b için trailing YASAK)
    if "S0002b" in strategy_file.name:
        if "trailing_stop = True" in py_code:
            errors.append(
                f"{strategy_file.name}: Kart A sabit 1 ATR stop gerektirir, trailing YASAK!"
            )
        if "trade.stop_loss != self.stoploss" not in py_code:
            errors.append(
                f"{strategy_file.name}: custom_stoploss sabit stop koruma kontrolü içermiyor!"
            )

    return errors


def main() -> None:
    strat_dir = REPO / "user_data" / "strategies"
    hypo_dir = REPO / "docs" / "hypotheses"

    all_errors = []
    for strat in strat_dir.glob("S*.py"):
        base = strat.stem
        # Match hypothesis card e.g. S0002bVolumeMomentum -> S-0002b.md
        hypo_id = base[:5]
        if len(base) > 5 and base[5].isalpha():
            hypo_id = base[:6]
        hypo_id = hypo_id[:1] + "-" + hypo_id[1:]
        card = hypo_dir / f"{hypo_id}.md"
        if card.exists():
            errs = check_alignment(strat, card)
            all_errors.extend(errs)

    if all_errors:
        print("[HATA] Kart ↔ Kod Uyum Denetimi Başarısız:")
        for e in all_errors:
            print(" -", e)
        sys.exit(1)
    else:
        print("[OK] Kart ↔ Kod Uyum Denetimi Başarılı!")


if __name__ == "__main__":
    main()
