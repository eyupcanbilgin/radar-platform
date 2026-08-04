"""Producer scheduling: collect through the hour, publish once the hour has closed.

Two cadences, one loop:

- **collect** runs every ``collect_interval_seconds``.  It must run throughout the hour
  because the hourly open-interest endpoint only retains about 30 days; anything older can
  exist only because we stored it while it was still being served.
- **publish** runs once per closed UTC hour, after a short grace.  The grace is deliberately
  shorter than the signal service's own 90s read grace, so the context artifact exists before
  the consumer looks for it.

Failure policy: a failed task is recorded and the loop continues.  Stopping the daemon on a
transient HTTP error would guarantee a hole in the series, which is the exact failure this
component exists to prevent.  Nothing is retried inside a tick; the next tick is the retry.

Catch-up is bounded and labelled.  After downtime the scheduler may publish a limited number
of missed hours, each marked ``catch_up`` so a late artifact is never mistaken for live
operation.  Hours beyond that bound are reported as an explicit ``skipped`` run — a silently
dropped window would read as "we covered everything".
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from btc_radar.core.heartbeat import HeartbeatStore

DEFAULT_COLLECT_INTERVAL_SECONDS = 300
#: radar-signal 90 sn sonra okur; context o okumadan önce yerinde olmalı (ADR-0006).
DEFAULT_PUBLISH_GRACE_SECONDS = 45
MAX_WAIT_SECONDS = 60.0

TASK_COLLECT = "collect"
TASK_PUBLISH = "publish"

Clock = Callable[[], datetime]


def latest_due_hour(now_utc: datetime, *, grace_seconds: int) -> datetime:
    """En son kapanmış ve grace süresi dolmuş UTC saat sınırı."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc timezone-aware olmalı")
    if not 0 <= grace_seconds < 3600:
        raise ValueError("grace_seconds 0..3599 aralığında olmalı")
    now_utc = now_utc.astimezone(UTC)
    boundary = now_utc.replace(minute=0, second=0, microsecond=0)
    if now_utc < boundary + timedelta(seconds=grace_seconds):
        boundary -= timedelta(hours=1)
    return boundary


@dataclass(frozen=True)
class ScheduledRun:
    """One task attempt, in the shape the daemon prints and the heartbeat stores."""

    task: str
    status: str
    started_at: datetime
    finished_at: datetime
    as_of: datetime | None = None
    catch_up: bool = False
    consecutive_failures: int = 0
    detail: dict = field(default_factory=dict)

    def as_payload(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "as_of": None if self.as_of is None else self.as_of.isoformat(),
            "catch_up": self.catch_up,
            "consecutive_failures": self.consecutive_failures,
            "detail": self.detail,
        }


class ProducerScheduler:
    """Deterministic tick core; the daemon loop only advances the clock."""

    def __init__(
        self,
        *,
        collect: Callable[[], dict],
        publish: Callable[[datetime], dict],
        heartbeat: HeartbeatStore,
        clock: Clock | None = None,
        collect_interval_seconds: int = DEFAULT_COLLECT_INTERVAL_SECONDS,
        publish_grace_seconds: int = DEFAULT_PUBLISH_GRACE_SECONDS,
        catch_up_hours: int = 0,
    ) -> None:
        if collect_interval_seconds <= 0:
            raise ValueError("collect_interval_seconds > 0 olmalı")
        if not 0 <= publish_grace_seconds < 3600:
            raise ValueError("publish_grace_seconds 0..3599 aralığında olmalı")
        if catch_up_hours < 0:
            raise ValueError("catch_up_hours >= 0 olmalı")
        self._collect = collect
        self._publish = publish
        self._heartbeat = heartbeat
        self._clock = clock or (lambda: datetime.now(UTC))
        self.collect_interval_seconds = collect_interval_seconds
        self.publish_grace_seconds = publish_grace_seconds
        self.catch_up_hours = catch_up_hours

    def now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("scheduler clock timezone-aware UTC olmalı")
        return value.astimezone(UTC)

    def tick(self) -> list[ScheduledRun]:
        """Run whatever is due right now. Never raises for a task failure."""
        runs: list[ScheduledRun] = []
        now = self.now()

        # Toplama önce: yayınlanacak saatin verisi deponun içinde olsun.
        if self._collect_due(now):
            runs.append(self._run(TASK_COLLECT, lambda: self._collect()))

        pending, skipped = self._plan_publishes(now)
        if skipped is not None:
            runs.append(self._record_skip(skipped))
        for as_of, catch_up in pending:
            runs.append(
                self._run(
                    TASK_PUBLISH,
                    lambda hour=as_of: self._publish(hour),
                    as_of=as_of,
                    catch_up=catch_up,
                )
            )
        return runs

    def serve_forever(
        self,
        *,
        stop_event: threading.Event,
        on_run: Callable[[ScheduledRun], None],
        wait: Callable[[float], None] | None = None,
    ) -> None:
        """Loop until ``stop_event`` is set, sleeping only until the next due moment."""
        sleeper = wait or (lambda seconds: stop_event.wait(timeout=seconds))
        while not stop_event.is_set():
            for run in self.tick():
                on_run(run)
            if stop_event.is_set():
                break
            sleeper(self.seconds_until_next_wake())

    def seconds_until_next_wake(self) -> float:
        now = self.now()
        candidates = [self._next_collect_at(now), self._next_publish_at(now)]
        remaining = min((moment - now).total_seconds() for moment in candidates)
        # Duvar saati düzeltmeleri ve durdurma sinyali için düzenli uyanma.
        return max(0.1, min(remaining, MAX_WAIT_SECONDS))

    def _collect_due(self, now: datetime) -> bool:
        return now >= self._next_collect_at(now)

    def _next_collect_at(self, now: datetime) -> datetime:
        # Son DENEME temel alınır; başarısız uç, döngüyü hızlı retry'a çevirmemeli.
        last = self._heartbeat.last_run(TASK_COLLECT)
        if last is None:
            return now
        finished = datetime.fromisoformat(last["finished_at"]).astimezone(UTC)
        return finished + timedelta(seconds=self.collect_interval_seconds)

    def _next_publish_at(self, now: datetime) -> datetime:
        due = latest_due_hour(now, grace_seconds=self.publish_grace_seconds)
        published = self._heartbeat.latest_success_as_of(TASK_PUBLISH)
        if published is None or published < due:
            return now
        return due + timedelta(hours=1, seconds=self.publish_grace_seconds)

    def _plan_publishes(self, now: datetime) -> tuple[list[tuple[datetime, bool]], dict | None]:
        due = latest_due_hour(now, grace_seconds=self.publish_grace_seconds)
        published = self._heartbeat.latest_success_as_of(TASK_PUBLISH)
        if published is None:
            # İlk koşu geçmişi yeniden yayınlamaz: hangi geçmişin yayınlanacağı bir karardır.
            return [(due, False)], None
        if published >= due:
            return [], None

        missed: list[datetime] = []
        cursor = published + timedelta(hours=1)
        while cursor <= due:
            missed.append(cursor)
            cursor += timedelta(hours=1)

        allowed = self.catch_up_hours + 1  # `due` her zaman yayınlanır
        dropped = missed[:-allowed] if len(missed) > allowed else []
        pending = missed[-allowed:]
        skip_report = (
            None
            if not dropped
            else {
                "reason": "catch_up_window_exceeded",
                "dropped_hours": len(dropped),
                "oldest_missed_as_of": dropped[0].isoformat(),
                "newest_missed_as_of": dropped[-1].isoformat(),
                "catch_up_hours": self.catch_up_hours,
            }
        )
        return [(hour, hour != due) for hour in pending], skip_report

    def _record_skip(self, detail: dict) -> ScheduledRun:
        moment = self.now()
        self._heartbeat.record(
            task=TASK_PUBLISH,
            status="skipped",
            started_at=moment,
            finished_at=moment,
            detail=detail,
        )
        return ScheduledRun(
            task=TASK_PUBLISH,
            status="skipped",
            started_at=moment,
            finished_at=moment,
            detail=detail,
        )

    def _run(
        self,
        task: str,
        action: Callable[[], dict],
        *,
        as_of: datetime | None = None,
        catch_up: bool = False,
    ) -> ScheduledRun:
        started_at = self.now()
        try:
            detail = dict(action())
            status = "ok"
        except Exception as error:  # tek bir hata toplayıcıyı öldürmemeli
            detail = {
                "error_type": type(error).__name__,
                "error": " ".join(str(error).split())[:500],
            }
            status = "error"
        finished_at = self.now()
        if catch_up:
            detail = {**detail, "catch_up": True}
        self._heartbeat.record(
            task=task,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            as_of=as_of,
            detail=detail,
        )
        return ScheduledRun(
            task=task,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            as_of=as_of,
            catch_up=catch_up,
            consecutive_failures=self._heartbeat.consecutive_failures(task),
            detail=detail,
        )
