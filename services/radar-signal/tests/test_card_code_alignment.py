"""ADIM 3 — Kart ↔ Kod Uyum Denetimi Birim Testleri."""

from pathlib import Path

from check_card_code_alignment import check_alignment

REPO = Path(__file__).resolve().parent.parent


def test_card_code_alignment_s0002b():
    strat = REPO / "user_data" / "strategies" / "S0002bVolumeMomentum.py"
    card = REPO / "docs" / "hypotheses" / "S-0002b.md"
    assert strat.exists()
    assert card.exists()

    errors = check_alignment(strat, card)
    assert not errors, f"Uyum hataları bulundu: {errors}"
