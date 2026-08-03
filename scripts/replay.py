"""Replay determinizm koşucusu — aynı veri + aynı ortam → bit-bit aynı sinyal.

Kaydedilmiş sinyal olaylarını (fixture) N kez boru hattından geçirir ve üretilen
mesaj gövdelerinin/durumlarının parmak izini karşılaştırır. Ortam parmak izi
(lockfile hash dahil, ŞART A) rapora yazılır.

Kullanım:
    .venv/Scripts/python scripts/replay.py --runs 100
    .venv/Scripts/python scripts/replay.py --runs 10 --events tests/fixtures/events.json
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from provenance import environment_fingerprint  # noqa: E402

from enricher.ledger import SignalLedger  # noqa: E402
from enricher.outbox import Outbox  # noqa: E402
from enricher.pipeline import SignalEvent, SignalPipeline  # noqa: E402
from enricher.policy import load_lifecycle  # noqa: E402

DEFAULT_EVENTS = REPO / "tests" / "fixtures" / "signal_events.json"


class _Collector:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, body: str) -> None:
        self.sent.append(body)


def load_events(path: Path) -> list[SignalEvent]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    events = []
    for item in raw:
        item = dict(item)
        item["candle_close_utc"] = datetime.fromisoformat(item["candle_close_utc"])
        events.append(SignalEvent(**item))
    return events


def run_once(events: list[SignalEvent], lifecycle: dict) -> str:
    """Bir replay turu; çıktının deterministik parmak izini döndürür."""
    with SignalLedger() as led, Outbox() as ob:
        pipe = SignalPipeline(ledger=led, outbox=ob, lifecycle=lifecycle)
        sender = _Collector()
        results = []
        for ev in events:
            res = pipe.handle(ev, now=ev.candle_close_utc)
            results.append((res.signal_id, res.state.value, res.block_reason or ""))
            pipe.deliver(sender, now=ev.candle_close_utc)
        payload = {"results": results, "messages": sender.sent}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    args = ap.parse_args()

    fingerprint = environment_fingerprint()
    events = load_events(args.events)
    lifecycle = load_lifecycle()

    digests = {run_once(events, lifecycle) for _ in range(args.runs)}

    print("Ortam parmak izi:")
    for key, value in sorted(fingerprint.items()):
        shown = value if isinstance(value, bool) else f"{value[:16]}..."
        print(f"  {key:18} {shown}")
    print(f"\n{args.runs} replay · {len(events)} olay · farklı sonuç sayısı: {len(digests)}")
    if len(digests) != 1:
        sys.exit(f"DETERMİNİZM İHLALİ: {len(digests)} farklı çıktı üretildi")
    print(f"OK: bit-bit özdeş (çıktı hash {next(iter(digests))[:16]}...)")
    if fingerprint["git_dirty"]:
        print("UYARI: çalışma ağacı kirli — bu sonuç 'final' etiketi alamaz (kural 7)")


if __name__ == "__main__":
    main()
