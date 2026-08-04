"""Public Binance USD-M historical funding and open-interest provider.

Source URLs:
- https://fapi.binance.com/fapi/v1/fundingRate (settled funding payments)
- https://fapi.binance.com/futures/data/openInterestHist (period-sampled open interest)

Rate limits (Binance docs + live probe, 2026-08-04): ``fundingRate`` accepts ``limit`` up
to 1000, ``openInterestHist`` up to 500.  Both are keyless and single-symbol here.

Known quirks — every one of these was verified against the live API on 2026-08-04, not
copied from documentation:

- ``fundingRate`` honours ``startTime`` and pages FORWARD from it in ascending order.
  A ``startTime`` 400 days back still returns data.
- ``openInterestHist`` does NOT anchor on ``startTime`` alone: given only ``startTime`` it
  returns the TAIL of ``[startTime, now]``, i.e. the newest ``limit`` rows.  Paging
  therefore walks BACKWARD through ``endTime``.  Sending both bounds returns the window.
- ``openInterestHist`` retains roughly 30 days.  A ``startTime`` older than that is a hard
  error (``{"code":-1130,"msg":"parameter 'startTime' is invalid."}``), not an empty list.
  This is why the hourly OI series must be collected continuously: history beyond the
  retention window can only exist because we stored it ourselves.
- ``fundingTime`` carries millisecond jitter around the 8h boundary (``…800004``), so the
  settlement series must never be assumed to land exactly on the hour.
- ``lastFundingRate`` from ``premiumIndex`` is the running estimate for the OPEN period,
  while ``fundingRate`` here is the SETTLED payment.  They are different series and are
  stored under different metric names on purpose.

Availability semantics (ADR-0005): a backfilled row is stamped
``available_at = event_time + publication_lag``, i.e. the exchange publication instant, not
the moment our backfill happened to run.  ``ingested_at`` and the distinct provider name
keep "when we actually learned it" separable, so a backfill can never be presented as
evidence of uninterrupted live operation.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider
from btc_radar.providers.binance_http import BinancePublicClient

FUNDING_SETTLED_METRIC = "funding_rate_settled"
OPEN_INTEREST_HOURLY_METRIC = "open_interest_1h"
OPEN_INTEREST_VALUE_HOURLY_METRIC = "open_interest_value_1h"

#: Observed retention of ``openInterestHist``; an older ``startTime`` is rejected outright.
OPEN_INTEREST_HISTORY_RETENTION_DAYS = 30
_BINANCE_INVALID_START_TIME_CODE = -1130


class HistoryWindowError(RuntimeError):
    """The requested window is outside what the endpoint still retains."""


class BinanceFuturesHistoryProvider(BinancePublicClient, BaseProvider):
    """Normalize settled funding and hourly open-interest history into PIT rows.

    ``fetch(FUNDING_SETTLED_METRIC, start_time=..., limit=...)`` pages forward.
    ``fetch(OPEN_INTEREST_HOURLY_METRIC, end_time=..., limit=...)`` pages backward and
    returns TWO metrics per record: contract open interest and its USDT notional.
    """

    name: ClassVar[str] = "binance_futures_history"
    source_group: ClassVar[str] = "derivatives"
    supported_metrics: ClassVar[frozenset[str]] = frozenset(
        {FUNDING_SETTLED_METRIC, OPEN_INTEREST_HOURLY_METRIC}
    )

    _FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
    _OPEN_INTEREST_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
    _FUNDING_MAX_LIMIT = 1000
    _OPEN_INTEREST_MAX_LIMIT = 500
    _OPEN_INTEREST_PERIOD = "1h"

    def __init__(self, *args: Any, publication_lag_seconds: float, **kwargs: Any) -> None:
        """``publication_lag_seconds`` is supplied by the caller from config, never guessed.

        The lag is what keeps a value stamped exactly on an hour boundary out of the
        decision taken at that same boundary.
        """
        super().__init__(*args, **kwargs)
        if publication_lag_seconds < 0:
            raise ValueError("publication_lag_seconds >= 0 olmali")
        self._publication_lag = timedelta(seconds=publication_lag_seconds)

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch one page of history for the requested metric family."""
        self._validate_symbol(params.pop("symbol", "BTCUSDT"))
        if metric == FUNDING_SETTLED_METRIC:
            return await self._fetch_funding(**params)
        if metric == OPEN_INTEREST_HOURLY_METRIC:
            return await self._fetch_open_interest(**params)
        allowed = ", ".join(sorted(self.supported_metrics))
        raise ValueError(f"desteklenmeyen Binance gecmis metrigi: {metric!r}; izinli: {allowed}")

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        if symbol != "BTCUSDT":
            raise ValueError("bu provider yalniz BTCUSDT sembolunu destekler")

    @staticmethod
    def _require_utc(value: datetime, *, field: str) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"{field} timezone-aware UTC olmali")
        return value.astimezone(UTC)

    @staticmethod
    def _epoch_millis(value: datetime) -> int:
        return int(value.timestamp() * 1000)

    def _validate_limit(self, limit: int, *, maximum: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit tam sayi olmali")
        if not 1 <= limit <= maximum:
            raise ValueError(f"limit [1,{maximum}] araliginda olmali; gelen: {limit}")
        return limit

    async def _fetch_funding(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[RawObservation]:
        params: dict[str, Any] = {
            "symbol": "BTCUSDT",
            "limit": self._validate_limit(limit, maximum=self._FUNDING_MAX_LIMIT),
        }
        if start_time is not None:
            params["startTime"] = self._epoch_millis(
                self._require_utc(start_time, field="start_time")
            )
        if end_time is not None:
            params["endTime"] = self._epoch_millis(self._require_utc(end_time, field="end_time"))

        payload, retrieved_at = await self._request_history(self._FUNDING_URL, params)
        observations: list[RawObservation] = []
        previous: datetime | None = None
        for record in payload:
            event_time = self._record_time(record, field="fundingTime", previous=previous)
            previous = event_time
            observations.append(
                RawObservation(
                    timestamp_utc=event_time,
                    retrieved_at_utc=retrieved_at,
                    available_at_utc=event_time + self._publication_lag,
                    asset="BTC",
                    venue="binance_futures",
                    metric=FUNDING_SETTLED_METRIC,
                    raw_value=self._number(record, "fundingRate"),
                    unit="ratio",
                    source_group=self.source_group,
                    source_url=self._FUNDING_URL,
                    quality=1.0,
                    notes=f"settled funding; rate_type={record.get('rateType', 'unknown')}",
                )
            )
        return observations

    async def _fetch_open_interest(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[RawObservation]:
        params: dict[str, Any] = {
            "symbol": "BTCUSDT",
            "period": self._OPEN_INTEREST_PERIOD,
            "limit": self._validate_limit(limit, maximum=self._OPEN_INTEREST_MAX_LIMIT),
        }
        if start_time is not None:
            params["startTime"] = self._epoch_millis(
                self._require_utc(start_time, field="start_time")
            )
        if end_time is not None:
            params["endTime"] = self._epoch_millis(self._require_utc(end_time, field="end_time"))

        payload, retrieved_at = await self._request_history(self._OPEN_INTEREST_HIST_URL, params)
        observations: list[RawObservation] = []
        previous: datetime | None = None
        for record in payload:
            event_time = self._record_time(record, field="timestamp", previous=previous)
            previous = event_time
            available_at = event_time + self._publication_lag
            observations.append(
                RawObservation(
                    timestamp_utc=event_time,
                    retrieved_at_utc=retrieved_at,
                    available_at_utc=available_at,
                    asset="BTC",
                    venue="binance_futures",
                    metric=OPEN_INTEREST_HOURLY_METRIC,
                    raw_value=self._number(record, "sumOpenInterest", minimum=0.0),
                    unit="BTC",
                    window=self._OPEN_INTEREST_PERIOD,
                    source_group=self.source_group,
                    source_url=self._OPEN_INTEREST_HIST_URL,
                    quality=1.0,
                    notes="Binance USD-M hourly open interest bucket",
                )
            )
            observations.append(
                RawObservation(
                    timestamp_utc=event_time,
                    retrieved_at_utc=retrieved_at,
                    available_at_utc=available_at,
                    asset="BTC",
                    venue="binance_futures",
                    metric=OPEN_INTEREST_VALUE_HOURLY_METRIC,
                    raw_value=self._number(record, "sumOpenInterestValue", minimum=0.0),
                    unit="USDT",
                    window=self._OPEN_INTEREST_PERIOD,
                    source_group=self.source_group,
                    source_url=self._OPEN_INTEREST_HIST_URL,
                    quality=1.0,
                    notes="Binance USD-M hourly open interest notional",
                )
            )
        return observations

    async def _request_history(
        self, url: str, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], datetime]:
        try:
            payload, retrieved_at = await self._request_json(url, params, expect=list)
        except httpx.HTTPStatusError as error:
            self._raise_if_window_error(error, url=url)
            raise
        for record in payload:
            if not isinstance(record, dict):
                raise ValueError(
                    f"Binance gecmis yaniti dict kayitlardan olusmali; "
                    f"{type(record).__name__} geldi"
                )
            self._require_symbol(record)
        return payload, retrieved_at

    @staticmethod
    def _raise_if_window_error(error: httpx.HTTPStatusError, *, url: str) -> None:
        """Translate Binance's retention rejection into a named, actionable error."""
        if error.response.status_code != 400:
            return
        try:
            body = json.loads(error.response.text)
        except ValueError:
            return
        if not isinstance(body, dict) or body.get("code") != _BINANCE_INVALID_START_TIME_CODE:
            return
        raise HistoryWindowError(
            f"{url} saklama penceresi disinda bir zaman istendi "
            f"(~{OPEN_INTEREST_HISTORY_RETENTION_DAYS} gun); daha eski gecmis yalniz "
            "kendi PIT deponuzda olabilir"
        ) from error

    def _record_time(
        self, record: dict[str, Any], *, field: str, previous: datetime | None
    ) -> datetime:
        event_time = self._millis(record, field)
        if previous is not None and event_time <= previous:
            raise ValueError(
                f"Binance gecmis yaniti {field} alaninda artan sirada degil: "
                f"{previous.isoformat()} -> {event_time.isoformat()}"
            )
        return event_time
