"""Public Binance spot BTCUSDT historical hourly OHLCV provider.

Source URL:
- https://api.binance.com/api/v3/klines

Rate limit and pagination (Binance docs, verified 2026-08-05): keyless klines requests have
weight 2, accept ``startTime``/``endTime`` and at most 1000 rows, and return rows oldest-first
when ``startTime`` is present.

Known quirks:
- The endpoint may include a still-open final candle. History never normalizes a row whose
  close time is after either retrieval time or the requested end boundary.
- Historical availability is the candle close plus the configured publication lag, not the
  time this backfill happened to run. The distinct provider name and PIT ``ingested_at`` keep
  retrospective reconstruction separate from proof that the live collector was running.
- This provider cannot reconstruct spot/perp basis or order-book snapshots. Those endpoints
  expose current state only, so inventing historical rows from OHLCV would be false evidence.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from btc_radar.models.observation import RawObservation
from btc_radar.providers.binance_spot import OHLCV_METRIC, BinanceSpotProvider


class BinanceSpotHistoryProvider(BinanceSpotProvider):
    """Page closed hourly spot candles forward with point-in-time availability."""

    name: ClassVar[str] = "binance_spot_history"
    supported_metrics: ClassVar[frozenset[str]] = frozenset({OHLCV_METRIC})
    _MAX_LIMIT = 1000

    def __init__(self, *args: Any, publication_lag_seconds: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if publication_lag_seconds < 0:
            raise ValueError("publication_lag_seconds >= 0 olmali")
        self._publication_lag = timedelta(seconds=publication_lag_seconds)

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch one forward page using ``start_time``, ``end_time`` and ``limit``."""
        symbol = params.pop("symbol", "BTCUSDT")
        if symbol != "BTCUSDT":
            raise ValueError("bu provider yalniz BTCUSDT sembolunu destekler")
        if metric != OHLCV_METRIC:
            raise ValueError(f"desteklenmeyen Binance spot gecmis metrigi: {metric!r}")

        start = self._require_utc(params.pop("start_time", None), field="start_time")
        end = self._require_utc(params.pop("end_time", None), field="end_time")
        limit = self._validate_limit(params.pop("limit", self._MAX_LIMIT))
        if params:
            raise ValueError(f"desteklenmeyen Binance spot gecmis parametreleri: {sorted(params)}")
        if start is not None and end is not None and start >= end:
            raise ValueError("start_time end_time'dan once olmali")

        request: dict[str, Any] = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "limit": limit,
        }
        if start is not None:
            request["startTime"] = int(start.timestamp() * 1000)
        if end is not None:
            request["endTime"] = int(end.timestamp() * 1000)

        payload, retrieved_at = await self._request_json(self._KLINES_URL, request, expect=list)
        cutoff = min(retrieved_at, end) if end is not None else retrieved_at
        observations: list[RawObservation] = []
        previous_open: datetime | None = None
        for raw_row in payload:
            row = self._kline_row_dict(raw_row)
            open_time = self._millis(row, "open_time")
            close_time = self._millis(row, "close_time")
            if previous_open is not None and open_time <= previous_open:
                raise ValueError("Binance spot klines artan openTime sirasinda olmali")
            previous_open = open_time
            if start is not None and open_time < start:
                raise ValueError("Binance spot klines istenen start_time oncesi satir dondurdu")
            if close_time > cutoff:
                continue
            observations.extend(
                self._parse_ohlcv_row(
                    row,
                    retrieved_at=retrieved_at,
                    available_at=close_time + self._publication_lag,
                )
            )
        return observations

    @staticmethod
    def _require_utc(value: datetime | None, *, field: str) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f"{field} timezone-aware UTC olmali")
        return value.astimezone(UTC)

    def _validate_limit(self, limit: Any) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit tam sayi olmali")
        if not 1 <= limit <= self._MAX_LIMIT:
            raise ValueError(f"limit [1,{self._MAX_LIMIT}] araliginda olmali; gelen: {limit}")
        return limit
