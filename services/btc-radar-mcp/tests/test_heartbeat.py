"""Heartbeat log: append-only run history, failure visibility, operator summary."""

from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.heartbeat import HeartbeatStore

T0 = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def store():
    with HeartbeatStore() as heartbeat:
        yield heartbeat


def _record(store: HeartbeatStore, *, task="collect", status="ok", offset=0, **kwargs) -> int:
    moment = T0 + timedelta(seconds=offset)
    return store.record(
        task=task,
        status=status,
        started_at=moment,
        finished_at=moment + timedelta(milliseconds=250),
        **kwargs,
    )


def test_records_are_append_only_and_a_failure_is_never_erased(store):
    _record(store, status="error", detail={"error": "network down"}, offset=0)
    _record(store, status="ok", offset=300)

    assert store.count() == 2
    assert store.last_run("collect")["status"] == "ok"
    # Sonraki başarı, kesintinin kaydını silmez.
    rows = store._conn.execute("SELECT status FROM heartbeats ORDER BY id").fetchall()
    assert [row["status"] for row in rows] == ["error", "ok"]


def test_last_success_ignores_later_failures(store):
    _record(store, status="ok", offset=0)
    _record(store, status="error", offset=60, detail={"error": "boom"})

    assert store.last_run("collect")["status"] == "error"
    assert store.last_success("collect")["finished_at"].startswith("2026-08-04T12:00:00.250")


def test_latest_published_hour_comes_from_successful_runs_only(store):
    _record(store, task="publish", status="ok", as_of=T0, offset=10)
    _record(store, task="publish", status="error", as_of=T0 + timedelta(hours=1), offset=70)

    assert store.latest_success_as_of("publish") == T0


def test_consecutive_failures_resets_on_success(store):
    _record(store, status="error", offset=0)
    _record(store, status="error", offset=60)
    assert store.consecutive_failures("collect") == 2

    _record(store, status="ok", offset=120)
    assert store.consecutive_failures("collect") == 0


def test_skipped_runs_do_not_count_as_failures(store):
    _record(store, task="publish", status="error", offset=0)
    _record(store, task="publish", status="skipped", offset=30, detail={"reason": "window"})

    # "Atlandı" bir hata değil, bilinçli bir karardır; hata sayacını kirletmemeli.
    assert store.consecutive_failures("publish") == 1


def test_summary_reports_silence_since_the_last_success(store):
    _record(store, status="ok", offset=0)
    _record(store, status="error", offset=600, detail={"error": "timeout"})

    summary = {
        item["task"]: item
        for item in store.summary(now=T0 + timedelta(hours=1), tasks=("collect", "publish"))
    }

    collect = summary["collect"]
    assert collect["runs"] == 2
    assert collect["last_status"] == "error"
    assert collect["last_error"] == "timeout"
    assert collect["consecutive_failures"] == 1
    assert collect["seconds_since_last_success"] == pytest.approx(3599.75)

    # Hiç koşmamış görev de raporda görünür; sessizlik de bir bulgudur.
    assert summary["publish"]["runs"] == 0
    assert summary["publish"]["seconds_since_last_success"] is None


def test_naive_time_and_backwards_duration_fail_loud(store):
    with pytest.raises(ValueError, match="naive datetime"):
        store.record(
            task="collect",
            status="ok",
            started_at=datetime(2026, 8, 4, 12, 0),
            finished_at=T0,
        )
    with pytest.raises(ValueError, match="finished_at"):
        store.record(
            task="collect",
            status="ok",
            started_at=T0,
            finished_at=T0 - timedelta(seconds=1),
        )
