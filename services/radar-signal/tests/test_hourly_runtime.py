import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ccxt
import pytest

from decision_engine.features import LOOKBACK_BARS, build_feature_snapshot
from decision_engine.ledger import DecisionLedger
from decision_engine.runtime import (
    HourlyDecisionRuntime,
    UtcHourlyScheduler,
    latest_due_hour,
)
from decision_engine.sources import (
    BINANCE_SOURCE,
    BINANCE_SYMBOL,
    BINANCE_TIMEFRAME,
    BinanceUsdMClosedCandleSource,
    CandleBatch,
    CandleDataError,
    CandleNotReadyError,
    CandleTransportError,
    ExchangeClockError,
    JsonDecisionContextSource,
)
from scripts import run_hourly_decision as hourly_cli

T0 = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
SIGNAL_COMMIT = "1234567890ab"
PLATFORM_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_FIXTURE = (
    PLATFORM_ROOT / "contracts" / "decision-context" / "v1" / "examples" / "btc-1h-context.json"
)


def raw_rows_ending_at(end: datetime, count: int = LOOKBACK_BARS) -> list[list]:
    first_open = end - timedelta(hours=count)
    rows = []
    previous_close = 50_000.0
    for index in range(count):
        open_time = first_open + timedelta(hours=index)
        close = 50_000.0 + index * 11.0 + math.sin(index / 7.0) * 35.0
        open_price = previous_close
        rows.append(
            [
                int(open_time.timestamp() * 1000),
                open_price,
                max(open_price, close) + 25.0,
                min(open_price, close) - 25.0,
                close,
                1_000.0 + index * 3.0,
            ]
        )
        previous_close = close
    return rows


class FakeOhlcvClient:
    def __init__(self, *responses, server_time: datetime | Exception | None = None):
        self.responses = list(responses)
        self.server_time = server_time or (T0 + timedelta(seconds=90))
        self.calls = []
        self.time_calls = 0

    def fetch_time(self, params=None):
        self.time_calls += 1
        if isinstance(self.server_time, Exception):
            raise self.server_time
        return int(self.server_time.timestamp() * 1000)

    def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None, params=None):
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "since": since,
                "limit": limit,
                "params": params,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def candle_source(client, *, observed_at=T0 + timedelta(minutes=1, seconds=30), **kwargs):
    return BinanceUsdMClosedCandleSource(
        client,
        clock=lambda: observed_at,
        sleeper=kwargs.pop("sleeper", lambda _seconds: None),
        **kwargs,
    )


def context_payload_at(as_of: datetime) -> dict:
    payload = json.loads(CONTEXT_FIXTURE.read_text(encoding="utf-8"))
    stamp = as_of.isoformat().replace("+00:00", "Z")
    suffix = hashlib.sha256(stamp.encode()).hexdigest()
    payload["as_of_utc"] = stamp
    payload["snapshot"]["snapshot_id"] = "SNAP-" + suffix[:16]
    payload["snapshot"]["data_cutoff_at_utc"] = stamp
    payload["snapshot"]["computed_at_utc"] = (
        (as_of + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    )
    payload["snapshot"]["content_hash"] = suffix
    return payload


def write_context(source: JsonDecisionContextSource, as_of: datetime, payload: dict) -> Path:
    path = source.path_for(as_of_utc=as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def fetched_batch(as_of: datetime = T0) -> CandleBatch:
    rows = raw_rows_ending_at(as_of)
    client = FakeOhlcvClient(rows, server_time=as_of + timedelta(seconds=90))
    return candle_source(client, max_attempts=1).fetch_closed(as_of_utc=as_of)


def test_binance_source_requests_exact_closed_contract_window_and_filters_open_candle():
    rows = raw_rows_ending_at(T0)
    current_open = raw_rows_ending_at(T0 + timedelta(hours=1), 1)[0]
    client = FakeOhlcvClient([*rows, current_open])
    source = candle_source(client, max_attempts=1)

    batch = source.fetch_closed(as_of_utc=T0)

    assert len(batch.candles) == LOOKBACK_BARS
    assert batch.candles[-1].close_time_utc == T0
    assert batch.candles[-1].available_at_utc == T0
    assert batch.observed_at_utc > T0
    assert batch.exchange_time_utc == T0 + timedelta(seconds=90)
    assert batch.source == BINANCE_SOURCE
    assert client.calls == [
        {
            "symbol": BINANCE_SYMBOL,
            "timeframe": BINANCE_TIMEFRAME,
            "since": int((T0 - timedelta(hours=LOOKBACK_BARS)).timestamp() * 1000),
            "limit": LOOKBACK_BARS,
            "params": {"until": int(T0.timestamp() * 1000) - 1},
        }
    ]
    assert build_feature_snapshot(list(batch.candles), as_of=T0).ready is True


def test_same_market_rows_different_observation_times_keep_feature_identity():
    rows = raw_rows_ending_at(T0)
    first = candle_source(
        FakeOhlcvClient(rows), observed_at=T0 + timedelta(seconds=90), max_attempts=1
    ).fetch_closed(as_of_utc=T0)
    second = candle_source(
        FakeOhlcvClient(rows), observed_at=T0 + timedelta(minutes=10), max_attempts=1
    ).fetch_closed(as_of_utc=T0)
    assert first.observed_at_utc != second.observed_at_utc
    assert build_feature_snapshot(list(first.candles), as_of=T0) == build_feature_snapshot(
        list(second.candles), as_of=T0
    )


def test_exchange_clock_must_pass_close_grace_before_target_candle_is_eligible():
    rows = raw_rows_ending_at(T0)
    local_clock_ahead = T0 + timedelta(minutes=5)
    client = FakeOhlcvClient(rows, server_time=T0 + timedelta(seconds=89))
    source = candle_source(
        client,
        observed_at=local_clock_ahead,
        max_attempts=1,
        close_grace_seconds=90,
    )
    with pytest.raises(CandleNotReadyError, match="serverTime karar grace sınırına ulaşmadı"):
        source.fetch_closed(as_of_utc=T0)
    assert client.time_calls == 1
    assert client.calls == []


def test_unavailable_exchange_clock_never_freezes_an_unverified_slot(tmp_path: Path):
    client = FakeOhlcvClient(
        raw_rows_ending_at(T0),
        server_time=ccxt.RequestTimeout("server clock offline"),
    )
    source = candle_source(client, max_attempts=1)
    with DecisionLedger() as ledger:
        runtime = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=source,
            context_source=JsonDecisionContextSource(tmp_path),
            signal_commit=SIGNAL_COMMIT,
        )
        with pytest.raises(ExchangeClockError, match="serverTime 1 denemede alınamadı"):
            runtime.process_hour(as_of_utc=T0)
        assert ledger.count() == 0
    assert client.calls == []


def test_missing_target_candle_is_retried_then_returned_fail_closed():
    incomplete = raw_rows_ending_at(T0 - timedelta(hours=1), LOOKBACK_BARS - 1)
    delays = []
    client = FakeOhlcvClient(incomplete, incomplete, incomplete)
    batch = candle_source(
        client,
        max_attempts=3,
        retry_delays=(1.0, 2.0),
        sleeper=delays.append,
    ).fetch_closed(as_of_utc=T0)
    assert len(client.calls) == 3
    assert delays == [1.0, 2.0]
    feature = build_feature_snapshot(list(batch.candles), as_of=T0)
    assert feature.ready is False
    assert "decision_candle" in feature.missing_features


def test_transient_network_error_retries_but_rate_limit_does_not():
    rows = raw_rows_ending_at(T0)
    delays = []
    transient = FakeOhlcvClient(ccxt.RequestTimeout("temporary"), rows)
    batch = candle_source(
        transient,
        max_attempts=2,
        retry_delays=(1.0,),
        sleeper=delays.append,
    ).fetch_closed(as_of_utc=T0)
    assert len(batch.candles) == LOOKBACK_BARS
    assert len(transient.calls) == 2
    assert delays == [1.0]

    limited = FakeOhlcvClient(ccxt.RateLimitExceeded("slow down"), rows)
    with pytest.raises(CandleTransportError, match="hızlı retry yapılmadı"):
        candle_source(limited, max_attempts=2, retry_delays=(1.0,)).fetch_closed(as_of_utc=T0)
    assert len(limited.calls) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows + [rows[-1]],
        lambda rows: [*rows[:-1], [*rows[-1][:2], 1.0, 2.0, 3.0, rows[-1][5]]],
        lambda rows: [*rows[:-1], [rows[-1][0] + 1, *rows[-1][1:]]],
        lambda rows: [*rows[:-1], [*rows[-1][:-1], -1.0]],
        lambda rows: [[float("nan"), *rows[0][1:]], *rows[1:]],
    ],
)
def test_malformed_or_duplicate_ohlcv_is_rejected_without_synthesis(mutate):
    rows = mutate(raw_rows_ending_at(T0))
    with pytest.raises(CandleDataError):
        candle_source(FakeOhlcvClient(rows), max_attempts=1).fetch_closed(as_of_utc=T0)


def test_context_source_reads_only_exact_hour_contract(tmp_path: Path):
    source = JsonDecisionContextSource(tmp_path)
    exact_path = write_context(source, T0, context_payload_at(T0))
    result = source.read(as_of_utc=T0)
    assert result.status == "ready"
    assert result.path == exact_path
    assert result.context.as_of_utc == T0
    assert {source.read(as_of_utc=T0).context.model_dump_json() for _ in range(100)} == {
        result.context.model_dump_json()
    }


def test_context_source_never_falls_back_and_ignores_partial_temp_file(tmp_path: Path):
    source = JsonDecisionContextSource(tmp_path)
    write_context(source, T0 - timedelta(hours=1), context_payload_at(T0 - timedelta(hours=1)))
    target = source.path_for(as_of_utc=T0)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".json.tmp").write_text("{", encoding="utf-8")
    result = source.read(as_of_utc=T0)
    assert result.status == "missing"
    assert result.context is None


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        json.dumps({"unknown": True}),
        json.dumps(context_payload_at(T0 + timedelta(hours=1))),
    ],
)
def test_invalid_or_wrong_hour_context_fails_closed(tmp_path: Path, payload: str):
    source = JsonDecisionContextSource(tmp_path)
    path = source.path_for(as_of_utc=T0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    result = source.read(as_of_utc=T0)
    assert result.status == "invalid"
    assert result.context is None
    assert result.error


def test_non_utf8_context_fails_closed(tmp_path: Path):
    source = JsonDecisionContextSource(tmp_path)
    path = source.path_for(as_of_utc=T0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe")
    result = source.read(as_of_utc=T0)
    assert result.status == "invalid"
    assert result.context is None


def test_latest_due_hour_obeys_utc_grace_boundary():
    assert latest_due_hour(T0 + timedelta(seconds=89), grace_seconds=90) == T0 - timedelta(hours=1)
    assert latest_due_hour(T0 + timedelta(seconds=90), grace_seconds=90) == T0
    plus_three = (T0 + timedelta(hours=3, seconds=90)).astimezone(
        datetime.now().astimezone().tzinfo
    )
    assert latest_due_hour(plus_three, grace_seconds=90) == T0 + timedelta(hours=3)


class StaticCandleSource:
    def __init__(self, batch: CandleBatch):
        self.batch = batch
        self.calls = 0

    def fetch_closed(self, *, as_of_utc: datetime) -> CandleBatch:
        self.calls += 1
        assert as_of_utc == self.batch.requested_as_of_utc
        return self.batch


class FailingCandleSource:
    def __init__(self):
        self.calls = 0

    def fetch_closed(self, *, as_of_utc: datetime) -> CandleBatch:
        self.calls += 1
        raise CandleTransportError(f"offline at {as_of_utc.isoformat()}")


def test_runtime_with_real_candles_and_no_context_records_truthful_wait(tmp_path: Path):
    market = StaticCandleSource(fetched_batch())
    context_source = JsonDecisionContextSource(tmp_path / "contexts")
    with DecisionLedger(tmp_path / "decisions.sqlite") as ledger:
        runtime = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=market,
            context_source=context_source,
            signal_commit=SIGNAL_COMMIT,
            clock=lambda: T0 + timedelta(minutes=2),
        )
        result = runtime.process_hour(as_of_utc=T0)
        assert result.status == "created"
        assert result.feature.ready is True
        assert result.context_status == "missing"
        assert result.decision.outcome == "WAIT"
        assert result.decision.blockers == ["context:missing"]
        assert result.decision.real_orders is False


def test_ready_context_still_waits_without_accepted_directional_setup(tmp_path: Path):
    context_source = JsonDecisionContextSource(tmp_path / "contexts")
    write_context(context_source, T0, context_payload_at(T0))
    with DecisionLedger() as ledger:
        runtime = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=StaticCandleSource(fetched_batch()),
            context_source=context_source,
            signal_commit=SIGNAL_COMMIT,
            clock=lambda: T0 + timedelta(minutes=2),
        )
        result = runtime.process_hour(as_of_utc=T0)
        assert result.context_status == "ready"
        assert result.feature.ready is True
        assert result.decision.outcome == "WAIT"
        assert result.decision.reasons == ["no_directional_setup"]
        assert result.decision.blockers == []


def test_source_failure_freezes_wait_and_restart_does_not_refetch(tmp_path: Path):
    path = tmp_path / "decisions.sqlite"
    first_source = FailingCandleSource()
    with DecisionLedger(path) as ledger:
        runtime = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=first_source,
            context_source=JsonDecisionContextSource(tmp_path / "contexts"),
            signal_commit=SIGNAL_COMMIT,
            clock=lambda: T0 + timedelta(minutes=2),
        )
        first = runtime.process_hour(as_of_utc=T0)
        assert first.status == "created"
        assert first.candle_status == "unavailable"
        assert first.decision.outcome == "WAIT"
        assert "feature:decision_candle" in first.decision.blockers
        assert first_source.calls == 1

    replacement_source = StaticCandleSource(fetched_batch())
    with DecisionLedger(path) as ledger:
        restarted = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=replacement_source,
            context_source=JsonDecisionContextSource(tmp_path / "contexts"),
            signal_commit=SIGNAL_COMMIT,
        ).process_hour(as_of_utc=T0)
        assert restarted.status == "already_recorded"
        assert restarted.decision == first.decision
        assert restarted.candle_status == "not_checked"
        assert replacement_source.calls == 0


def test_scheduler_rejects_not_yet_due_explicit_hour(tmp_path: Path):
    now = T0 + timedelta(seconds=89)
    with DecisionLedger() as ledger:
        runtime = HourlyDecisionRuntime(
            ledger=ledger,
            candle_source=StaticCandleSource(fetched_batch()),
            context_source=JsonDecisionContextSource(tmp_path),
            signal_commit=SIGNAL_COMMIT,
        )
        scheduler = UtcHourlyScheduler(runtime, grace_seconds=90, clock=lambda: now)
        with pytest.raises(ValueError, match="henüz karar için hazır değil"):
            scheduler.run_once(as_of_utc=T0)
        assert ledger.count() == 0


def test_daemon_emits_each_due_slot_once_while_waking_for_clock_checks():
    clock_state = [T0 + timedelta(seconds=90)]

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        def process_hour(self, *, as_of_utc):
            self.calls.append(as_of_utc)
            return as_of_utc

    runtime = FakeRuntime()
    emitted = []

    class AdvancingStopEvent:
        def is_set(self):
            return len(runtime.calls) >= 2

        def wait(self, timeout):
            if not self.is_set():
                clock_state[0] += timedelta(seconds=timeout)
            return self.is_set()

    scheduler = UtcHourlyScheduler(runtime, grace_seconds=90, clock=lambda: clock_state[0])
    scheduler.serve_forever(stop_event=AdvancingStopEvent(), on_result=emitted.append)
    assert runtime.calls == [T0, T0 + timedelta(hours=1)]
    assert emitted == runtime.calls


def test_cli_explicit_commit_cannot_bypass_dirty_checkout(monkeypatch):
    monkeypatch.setattr(hourly_cli, "git_is_dirty", lambda: True)
    with pytest.raises(RuntimeError, match="çalışma ağacı kirli"):
        hourly_cli._signal_commit(SIGNAL_COMMIT)


def test_cli_explicit_commit_must_match_checkout_or_be_packaged(monkeypatch):
    monkeypatch.setattr(hourly_cli, "git_is_dirty", lambda: False)
    monkeypatch.setattr(hourly_cli, "git_commit", lambda: SIGNAL_COMMIT)
    assert hourly_cli._signal_commit(SIGNAL_COMMIT) == SIGNAL_COMMIT
    with pytest.raises(RuntimeError, match="checkout ile uyuşmuyor"):
        hourly_cli._signal_commit("abcdef012345")

    def no_git():
        raise subprocess.CalledProcessError(128, ["git", "status"])

    monkeypatch.setattr(hourly_cli, "git_is_dirty", no_git)
    assert hourly_cli._signal_commit(SIGNAL_COMMIT) == SIGNAL_COMMIT
    with pytest.raises(RuntimeError, match="--signal-commit zorunlu"):
        hourly_cli._signal_commit(None)


def test_cli_historical_as_of_uses_separate_replay_ledger_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RADAR_SIGNAL_DB_DIR", str(tmp_path))
    assert hourly_cli._ledger_path(None, as_of=None) == tmp_path / "hourly-decisions.sqlite"
    assert hourly_cli._ledger_path(None, as_of=T0) == tmp_path / "hourly-replay.sqlite"
    explicit = tmp_path / "explicit.sqlite"
    assert hourly_cli._ledger_path(explicit, as_of=T0) == explicit
