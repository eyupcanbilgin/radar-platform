"""Import every module needed by the supervised macOS paper runtime."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_engine.context_sets import load_context_set  # noqa: E402
from decision_engine.runtime import HourlyDecisionRuntime  # noqa: E402
from decision_engine.sources import BinanceUsdMClosedCandleSource  # noqa: E402
from enricher.telegram import sender_from_environment  # noqa: E402
from scripts.f0001_forward_coverage import main as coverage_main  # noqa: E402
from scripts.pump import main as pump_main  # noqa: E402
from scripts.run_hourly_decision import build_parser as build_hourly_parser  # noqa: E402

FORBIDDEN_RESEARCH_PACKAGES = ("freqtrade", "numpy", "pandas", "pyarrow")


def main() -> None:
    """Fail when a runtime import is missing or a research package leaked in."""
    runtime_symbols = (
        load_context_set,
        HourlyDecisionRuntime,
        BinanceUsdMClosedCandleSource,
        sender_from_environment,
        coverage_main,
        pump_main,
        build_hourly_parser,
    )
    if not all(callable(symbol) for symbol in runtime_symbols):
        raise RuntimeError("paper runtime import yüzeyi eksik")

    leaked = [name for name in FORBIDDEN_RESEARCH_PACKAGES if importlib.util.find_spec(name)]
    if leaked:
        raise RuntimeError(f"araştırma paketi runtime ortamına sızdı: {', '.join(leaked)}")


if __name__ == "__main__":
    main()
