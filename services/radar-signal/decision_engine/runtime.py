"""UTC hourly orchestration around market/context sources and the immutable ledger."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from decision_engine.decision import DecisionCardV1
from decision_engine.features import FeatureSnapshotV1
from decision_engine.ledger import DecisionLedger
from decision_engine.service import HourlyDecisionService
from decision_engine.sources import (
    CandleBatch,
    CandleSourceError,
    ContextRead,
    require_utc_hour,
)

DEFAULT_GRACE_SECONDS = 90
#: Bir saatin context'i henüz yayınlanmamışsa daemon'un bekleyeceği üst sınır.
#: ADR-0006 "producer grace < signal grace ⇒ producer önce yayınlar" sıralamasına dayanır;
#: fakat host uyku/uyanmasından sonra iki daemon aynı anda devam ettiği için o sıralama
#: geçersizdir (ADR-0041). Bu bütçe sıralamayı uyanma anında yeniden kurar.
DEFAULT_CONTEXT_WAIT_SECONDS = 240
#: Bekleme sırasındaki yoklama aralığı; bütçe dolmadan context belirirse hemen ilerlenir.
DEFAULT_CONTEXT_POLL_SECONDS = 5


class ClosedCandleSource(Protocol):
    def fetch_closed(self, *, as_of_utc: datetime) -> CandleBatch: ...


class DecisionContextSource(Protocol):
    def read(self, *, as_of_utc: datetime) -> ContextRead: ...


RunStatus = Literal["created", "idempotent", "already_recorded"]
SourceStatus = Literal["fetched", "unavailable", "not_checked"]
RuntimeContextStatus = Literal["ready", "missing", "invalid", "io_error", "not_checked"]


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _brief_error(error: Exception) -> str:
    message = " ".join(str(error).split())[:240]
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def latest_due_hour(now_utc: datetime, *, grace_seconds: int = DEFAULT_GRACE_SECONDS) -> datetime:
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
class RuntimeResult:
    status: RunStatus
    as_of_utc: datetime
    feature: FeatureSnapshotV1
    decision: DecisionCardV1
    candle_status: SourceStatus
    candle_count: int | None
    candle_source: str | None
    candle_observed_at_utc: datetime | None
    candle_exchange_time_utc: datetime | None
    candle_error: str | None
    context_status: RuntimeContextStatus
    context_path: str | None
    context_error: str | None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "as_of_utc": _utc_iso(self.as_of_utc),
            "decision_id": self.decision.decision_id,
            "outcome": self.decision.outcome,
            "reasons": self.decision.reasons,
            "blockers": self.decision.blockers,
            "feature_snapshot_id": self.feature.snapshot_id,
            "feature_ready": self.feature.ready,
            "missing_features": self.feature.missing_features,
            "candle_status": self.candle_status,
            "candle_count": self.candle_count,
            "candle_source": self.candle_source,
            "candle_observed_at_utc": (
                _utc_iso(self.candle_observed_at_utc)
                if self.candle_observed_at_utc is not None
                else None
            ),
            "candle_exchange_time_utc": (
                _utc_iso(self.candle_exchange_time_utc)
                if self.candle_exchange_time_utc is not None
                else None
            ),
            "candle_error": self.candle_error,
            "context_status": self.context_status,
            "context_path": self.context_path,
            "context_error": self.context_error,
            "real_orders": self.decision.real_orders,
            "signal_commit": self.decision.signal_commit,
        }


class HourlyDecisionRuntime:
    """Process one immutable hour. No setup source exists, so direction remains WAIT."""

    def __init__(
        self,
        *,
        ledger: DecisionLedger,
        candle_source: ClosedCandleSource,
        context_source: DecisionContextSource,
        signal_commit: str,
        clock: Callable[[], datetime] | None = None,
    ):
        self.ledger = ledger
        self.candle_source = candle_source
        self.context_source = context_source
        self.service = HourlyDecisionService(ledger, signal_commit=signal_commit)
        self.clock = clock or (lambda: datetime.now(UTC))

    def _already_recorded(self, *, as_of_utc: datetime, row: dict) -> RuntimeResult:
        feature = FeatureSnapshotV1.model_validate(row["feature_payload"])
        decision = DecisionCardV1.model_validate(row["decision_payload"])
        return RuntimeResult(
            status="already_recorded",
            as_of_utc=as_of_utc,
            feature=feature,
            decision=decision,
            candle_status="not_checked",
            candle_count=None,
            candle_source=None,
            candle_observed_at_utc=None,
            candle_exchange_time_utc=None,
            candle_error=None,
            context_status="not_checked",
            context_path=None,
            context_error=None,
        )

    def process_hour(self, *, as_of_utc: datetime) -> RuntimeResult:
        as_of_utc = require_utc_hour(as_of_utc)
        existing = self.ledger.get_for_period(as_of_utc=as_of_utc)
        if existing is not None:
            return self._already_recorded(as_of_utc=as_of_utc, row=existing)

        candle_status: SourceStatus = "fetched"
        candle_error = None
        candle_source = None
        candle_observed_at = None
        candle_exchange_time = None
        try:
            batch = self.candle_source.fetch_closed(as_of_utc=as_of_utc)
            candles = list(batch.candles)
            candle_count = len(candles)
            candle_source = batch.source
            candle_observed_at = batch.observed_at_utc
            candle_exchange_time = batch.exchange_time_utc
        except CandleSourceError as error:
            candles = []
            candle_count = 0
            candle_status = "unavailable"
            candle_error = _brief_error(error)

        context_read = self.context_source.read(as_of_utc=as_of_utc)
        context = context_read.context if context_read.status == "ready" else None
        recorded_at = self.clock()
        if recorded_at.tzinfo is None:
            raise ValueError("runtime clock timezone-aware olmalı")
        result = self.service.evaluate_and_record(
            candles=candles,
            context=context,
            as_of_utc=as_of_utc,
            # No accepted directional strategy exists; runtime cannot inject a setup.
            setup=None,
            recorded_at_utc=recorded_at.astimezone(UTC),
        )
        return RuntimeResult(
            status="created" if result.created else "idempotent",
            as_of_utc=as_of_utc,
            feature=result.feature,
            decision=result.decision,
            candle_status=candle_status,
            candle_count=candle_count,
            candle_source=candle_source,
            candle_observed_at_utc=candle_observed_at,
            candle_exchange_time_utc=candle_exchange_time,
            candle_error=candle_error,
            context_status=context_read.status,
            context_path=str(context_read.path),
            context_error=context_read.error,
        )


class UtcHourlyScheduler:
    """Thin scheduler; one-shot is the deterministic core, daemon only advances UTC slots."""

    def __init__(
        self,
        runtime: HourlyDecisionRuntime,
        *,
        grace_seconds: int = DEFAULT_GRACE_SECONDS,
        clock: Callable[[], datetime] | None = None,
        context_wait_seconds: int = DEFAULT_CONTEXT_WAIT_SECONDS,
        context_poll_seconds: int = DEFAULT_CONTEXT_POLL_SECONDS,
    ):
        if not 0 <= grace_seconds < 3600:
            raise ValueError("grace_seconds 0..3599 aralığında olmalı")
        if not 0 <= context_wait_seconds < 3600:
            raise ValueError("context_wait_seconds 0..3599 aralığında olmalı")
        if context_poll_seconds <= 0:
            raise ValueError("context_poll_seconds > 0 olmalı")
        self.runtime = runtime
        self.grace_seconds = grace_seconds
        self.context_wait_seconds = context_wait_seconds
        self.context_poll_seconds = context_poll_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def _context_missing(self, *, as_of_utc: datetime) -> bool:
        """Context yalnız "henüz yayınlanmadı" durumundaysa True.

        Yalnız ``missing`` bekletir: bu, "producer henüz yayınlamadı" demektir ve tam olarak
        düzeltilen yarıştır.  ``invalid``/``io_error`` artefaktın var ama bozuk olduğunu
        söyler; beklemek onu düzeltmez, fail-closed hemen çalışmalıdır.

        Karar defterinde o saat zaten varsa bekletilmez; ``process_hour`` idempotent döner.

        Yoklamanın tamamı en-iyi-çabadır: "context yalnızca henüz yayınlanmadı" olduğunu
        kesin saptayamazsak bekletmeyiz.  Davranış o zaman bugünküne iner ve gerçek durumu
        yetkili okuma (``process_hour``) deftere yazar.
        """
        try:
            if self.runtime.ledger.get_for_period(as_of_utc=as_of_utc) is not None:
                return False
            return self.runtime.context_source.read(as_of_utc=as_of_utc).status == "missing"
        except Exception:
            return False

    def run_once(self, *, as_of_utc: datetime | None = None) -> RuntimeResult:
        now = self.clock()
        due = latest_due_hour(now, grace_seconds=self.grace_seconds)
        if as_of_utc is None:
            as_of_utc = due
        else:
            as_of_utc = require_utc_hour(as_of_utc)
            if as_of_utc > due:
                raise ValueError(
                    f"as_of_utc henüz karar için hazır değil: as_of={_utc_iso(as_of_utc)}, "
                    f"latest_due={_utc_iso(due)}"
                )
        return self.runtime.process_hour(as_of_utc=as_of_utc)

    def serve_forever(
        self,
        *,
        stop_event: threading.Event,
        on_result: Callable[[RuntimeResult], None],
    ) -> None:
        last_processed_as_of: datetime | None = None
        # Bekleme bütçesi saat sınırından DEĞİL, o saatin ilk kez context'siz görüldüğü
        # andan ölçülür.  Host uykudan uyandığında duvar saati sınırın çok ötesindedir ama
        # producer o anda yayına yeni başlar; sınırdan ölçmek bütçeyi daha doğarken tüketirdi.
        pending_as_of: datetime | None = None
        pending_since: datetime | None = None
        while not stop_event.is_set():
            raw_now = self.clock()
            due = latest_due_hour(raw_now, grace_seconds=self.grace_seconds)
            now = raw_now.astimezone(UTC)
            if due != last_processed_as_of:
                if pending_as_of != due:
                    pending_as_of, pending_since = due, now
                waited = (now - pending_since).total_seconds()
                # Bekleme bu yuvayı asla aşamaz.  Bir sonraki saat due olduğu anda `due`
                # ilerler ve beklenen saat hiç yazılmadan düşerdi; saat kaybetmek, saati
                # context'siz yazmaktan daha kötüdür.
                slot_expires_at = due + timedelta(hours=1, seconds=self.grace_seconds)
                outlives_slot = (
                    now + timedelta(seconds=self.context_poll_seconds) >= slot_expires_at
                )
                if (
                    waited < self.context_wait_seconds
                    and not outlives_slot
                    and self._context_missing(as_of_utc=due)
                ):
                    # Karar yuvası saat başına tek ve değişmezdir; context yayınlanmadan
                    # yakmak o saati kalıcı olarak context'siz bırakır (ADR-0041).
                    stop_event.wait(timeout=self.context_poll_seconds)
                    continue
                result = self.run_once(as_of_utc=due)
                on_result(result)
                last_processed_as_of = due
                pending_as_of = pending_since = None
                raw_now = self.clock()
                due = latest_due_hour(raw_now, grace_seconds=self.grace_seconds)
                now = raw_now.astimezone(UTC)
            next_run = due + timedelta(hours=1, seconds=self.grace_seconds)
            remaining = max(0.1, (next_run - now).total_seconds())
            # Wake periodically for stop signals and wall-clock adjustments.
            stop_event.wait(timeout=min(remaining, 60.0))
