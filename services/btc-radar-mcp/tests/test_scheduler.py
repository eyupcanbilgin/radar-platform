"""Scheduler: two cadences, bounded catch-up, and failures that never stop the loop."""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from btc_radar.core.heartbeat import HeartbeatStore
from btc_radar.core.scheduler import (
    TASK_COLLECT,
    TASK_PUBLISH,
    ProducerScheduler,
    latest_due_hour,
)

START = datetime(2026, 8, 4, 12, 5, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


class Recorder:
    """Collect/publish stand-ins that record their calls and can be made to fail."""

    def __init__(self):
        self.collects = 0
        self.published: list[datetime] = []
        self.collect_error: Exception | None = None
        self.publish_error: Exception | None = None

    def collect(self) -> dict:
        if self.collect_error:
            raise self.collect_error
        self.collects += 1
        return {"inserted": 3}

    def publish(self, as_of: datetime) -> dict:
        if self.publish_error:
            raise self.publish_error
        self.published.append(as_of)
        return {"status": "created", "as_of_utc": as_of.isoformat()}


@pytest.fixture
def heartbeat():
    with HeartbeatStore() as store:
        yield store


def _scheduler(heartbeat, clock, recorder, **kwargs) -> ProducerScheduler:
    return ProducerScheduler(
        collect=recorder.collect,
        publish=recorder.publish,
        heartbeat=heartbeat,
        clock=clock,
        **kwargs,
    )


def test_latest_due_hour_waits_for_the_close_grace():
    assert latest_due_hour(datetime(2026, 8, 4, 12, 0, 30, tzinfo=UTC), grace_seconds=45) == (
        datetime(2026, 8, 4, 11, 0, tzinfo=UTC)
    )
    assert latest_due_hour(datetime(2026, 8, 4, 12, 1, tzinfo=UTC), grace_seconds=45) == (
        datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="grace_seconds"):
        latest_due_hour(datetime(2026, 8, 4, tzinfo=UTC), grace_seconds=3600)


def test_first_tick_collects_and_publishes_the_due_hour(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    runs = _scheduler(heartbeat, clock, recorder).tick()

    assert [(run.task, run.status) for run in runs] == [
        (TASK_COLLECT, "ok"),
        (TASK_PUBLISH, "ok"),
    ]
    assert recorder.collects == 1
    assert recorder.published == [datetime(2026, 8, 4, 12, 0, tzinfo=UTC)]
    assert runs[1].catch_up is False


def test_collect_waits_for_its_interval_and_publish_waits_for_the_next_hour(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, collect_interval_seconds=300)
    scheduler.tick()

    clock.advance(seconds=299)
    assert scheduler.tick() == []

    clock.advance(seconds=2)
    runs = scheduler.tick()
    assert [run.task for run in runs] == [TASK_COLLECT]
    assert recorder.collects == 2
    # Aynı saat ikinci kez yayınlanmaz; yeni saat açılınca yayın döner.
    assert recorder.published == [datetime(2026, 8, 4, 12, 0, tzinfo=UTC)]

    clock.advance(hours=1)
    runs = scheduler.tick()
    assert [run.task for run in runs] == [TASK_COLLECT, TASK_PUBLISH]
    assert recorder.published[-1] == datetime(2026, 8, 4, 13, 0, tzinfo=UTC)


def test_a_failing_endpoint_is_recorded_and_the_loop_survives(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    recorder.collect_error = RuntimeError("network down")
    scheduler = _scheduler(heartbeat, clock, recorder, collect_interval_seconds=60)

    first = scheduler.tick()
    assert first[0].status == "error"
    assert first[0].detail["error_type"] == "RuntimeError"
    assert first[0].consecutive_failures == 1
    # Yayın, toplama başarısız olsa bile denenir; ikisi ayrı görevdir.
    assert first[1].task == TASK_PUBLISH and first[1].status == "ok"

    # Hızlı retry yok: bir sonraki deneme yine interval sonrasıdır.
    clock.advance(seconds=30)
    assert scheduler.tick() == []

    clock.advance(seconds=31)
    second = scheduler.tick()
    assert second[0].consecutive_failures == 2

    recorder.collect_error = None
    clock.advance(seconds=61)
    third = scheduler.tick()
    assert third[0].status == "ok"
    assert third[0].consecutive_failures == 0


def test_a_failed_publish_is_retried_on_the_next_tick(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    recorder.publish_error = RuntimeError("disk full")
    scheduler = _scheduler(heartbeat, clock, recorder, collect_interval_seconds=60)

    assert scheduler.tick()[1].status == "error"

    recorder.publish_error = None
    clock.advance(seconds=61)
    runs = scheduler.tick()
    assert [run.task for run in runs] == [TASK_COLLECT, TASK_PUBLISH]
    assert recorder.published == [datetime(2026, 8, 4, 12, 0, tzinfo=UTC)]


def test_bounded_catch_up_publishes_missed_hours_and_labels_them(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, catch_up_hours=2)
    scheduler.tick()  # 12:00 yayınlandı

    clock.advance(hours=3)  # 13:00, 14:00 kaçırıldı, güncel saat 15:00
    runs = [run for run in scheduler.tick() if run.task == TASK_PUBLISH]

    assert [run.as_of.hour for run in runs] == [13, 14, 15]
    assert [run.catch_up for run in runs] == [True, True, False]
    assert all(run.detail.get("catch_up") for run in runs if run.catch_up)


def test_a_gap_beyond_the_catch_up_window_is_reported_not_silently_dropped(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, catch_up_hours=1)
    scheduler.tick()  # 12:00

    clock.advance(hours=6)  # 13:00..17:00 kaçırıldı, güncel 18:00
    runs = [run for run in scheduler.tick() if run.task == TASK_PUBLISH]

    skipped = [run for run in runs if run.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].detail["reason"] == "catch_up_window_exceeded"
    assert skipped[0].detail["dropped_hours"] == 4
    assert skipped[0].detail["oldest_missed_as_of"].startswith("2026-08-04T13:00")
    assert skipped[0].detail["newest_missed_as_of"].startswith("2026-08-04T16:00")
    assert [run.as_of.hour for run in runs if run.status == "ok"] == [17, 18]


def test_catch_up_disabled_publishes_only_the_current_hour(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, catch_up_hours=0)
    scheduler.tick()

    clock.advance(hours=4)
    runs = [run for run in scheduler.tick() if run.task == TASK_PUBLISH]

    assert [run.as_of.hour for run in runs if run.status == "ok"] == [16]
    assert [run.detail["dropped_hours"] for run in runs if run.status == "skipped"] == [3]


def test_first_run_does_not_backfill_history_it_never_saw(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, catch_up_hours=48)

    runs = [run for run in scheduler.tick() if run.task == TASK_PUBLISH]

    # Hangi geçmişin yayınlanacağı bir karardır; ilk koşu onu kendi başına vermez.
    assert [run.as_of.hour for run in runs] == [12]


def test_wake_interval_never_busy_loops_and_never_oversleeps(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, collect_interval_seconds=3600)
    scheduler.tick()

    assert 0.1 <= scheduler.seconds_until_next_wake() <= 60.0


def test_serve_forever_stops_on_the_stop_event(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    scheduler = _scheduler(heartbeat, clock, recorder, collect_interval_seconds=60)
    stop_event = threading.Event()
    seen = []

    def on_run(run) -> None:
        seen.append(run)
        if len([item for item in seen if item.task == TASK_COLLECT]) == 3:
            stop_event.set()

    scheduler.serve_forever(
        stop_event=stop_event,
        on_run=on_run,
        wait=lambda seconds: clock.advance(seconds=max(seconds, 60)),
    )

    assert recorder.collects == 3
    assert stop_event.is_set()


def test_scheduler_rejects_incoherent_configuration(heartbeat):
    clock, recorder = FakeClock(), Recorder()
    with pytest.raises(ValueError, match="collect_interval_seconds"):
        _scheduler(heartbeat, clock, recorder, collect_interval_seconds=0)
    with pytest.raises(ValueError, match="publish_grace_seconds"):
        _scheduler(heartbeat, clock, recorder, publish_grace_seconds=3600)
    with pytest.raises(ValueError, match="catch_up_hours"):
        _scheduler(heartbeat, clock, recorder, catch_up_hours=-1)
    with pytest.raises(ValueError, match="timezone-aware"):
        _scheduler(heartbeat, lambda: datetime(2026, 8, 4, 12), recorder).tick()
