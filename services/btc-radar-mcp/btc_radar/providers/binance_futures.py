"""Public Binance USD-M futures market-data provider.

Source URLs:
- https://fapi.binance.com/fapi/v1/premiumIndex (mark price + current funding rate)
- https://fapi.binance.com/fapi/v1/openInterest (current open interest)

Rate limits (Binance docs, 2026-08-04): both endpoints have IP weight 1 when a
single symbol is supplied.  This provider always sends ``symbol=BTCUSDT``; an
all-symbol request is intentionally impossible.

Known quirks:
- Numeric values arrive as strings and must be parsed fail-loud.
- ``nextFundingTime`` is a future schedule, not the funding observation time.
  The observation time for ``lastFundingRate`` is the response ``time`` field.
- Binance payload time can be slightly ahead of the local clock.  To prevent a
  future observation leaking through the PIT store, ``available_at`` is the
  later of response retrieval time and exchange event time.
- Historical funding/OI backfills have different availability semantics and
  are deliberately outside this current-snapshot provider.
"""

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


class BinanceFuturesProvider(BaseProvider):
    """Normalize the public BTCUSDT USD-M mark, funding, and OI snapshot."""

    name: ClassVar[str] = "binance_futures"
    source_group: ClassVar[str] = "derivatives"
    supported_metrics: ClassVar[frozenset[str]] = frozenset(
        {"mark_price", "funding_rate", "open_interest", "all"}
    )

    _PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
    _OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
    _HEADERS = {"User-Agent": "btc-radar/0.2 (public read-only market data)"}
    _RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        clock: Clock | None = None,
        sleep: Sleeper = asyncio.sleep,
        timeout_seconds: float = 5.0,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.25,
        max_retry_wait_seconds: float = 5.0,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds sonlu ve > 0 olmali")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts [1,5] araliginda olmali")
        if not math.isfinite(retry_base_seconds) or retry_base_seconds < 0:
            raise ValueError("retry_base_seconds sonlu ve >= 0 olmali")
        if not math.isfinite(max_retry_wait_seconds) or max_retry_wait_seconds < 0:
            raise ValueError("max_retry_wait_seconds sonlu ve >= 0 olmali")

        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._max_retry_wait_seconds = max_retry_wait_seconds

    async def __aenter__(self) -> "BinanceFuturesProvider":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close only a client created by this provider."""
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch one normalized metric or the deterministic three-metric bundle.

        Supported calls are ``fetch("mark_price")``, ``fetch("funding_rate")``,
        ``fetch("open_interest")`` and ``fetch("all")``.  ``symbol`` may be
        omitted or set to the only supported value, ``BTCUSDT``.
        """
        self._validate_call(metric, params)
        if metric == "all":
            premium, retrieved_premium = await self._request_json(self._PREMIUM_URL)
            oi, retrieved_oi = await self._request_json(self._OPEN_INTEREST_URL)
            return [
                self._parse_mark_price(premium, retrieved_premium),
                self._parse_funding_rate(premium, retrieved_premium),
                self._parse_open_interest(oi, retrieved_oi),
            ]
        if metric == "mark_price":
            payload, retrieved_at = await self._request_json(self._PREMIUM_URL)
            return [self._parse_mark_price(payload, retrieved_at)]
        if metric == "funding_rate":
            payload, retrieved_at = await self._request_json(self._PREMIUM_URL)
            return [self._parse_funding_rate(payload, retrieved_at)]

        payload, retrieved_at = await self._request_json(self._OPEN_INTEREST_URL)
        return [self._parse_open_interest(payload, retrieved_at)]

    def _validate_call(self, metric: str, params: dict[str, Any]) -> None:
        if metric not in self.supported_metrics:
            allowed = ", ".join(sorted(self.supported_metrics))
            raise ValueError(f"desteklenmeyen Binance USD-M metrigi: {metric!r}; izinli: {allowed}")
        unknown = sorted(set(params) - {"symbol"})
        if unknown:
            raise ValueError(f"desteklenmeyen Binance USD-M parametreleri: {unknown}")
        symbol = params.get("symbol", "BTCUSDT")
        if symbol != "BTCUSDT":
            raise ValueError("bu provider yalniz BTCUSDT sembolunu destekler")

    async def _request_json(self, url: str) -> tuple[dict[str, Any], datetime]:
        params = {"symbol": "BTCUSDT"}
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(
                    url,
                    params=params,
                    headers=self._HEADERS,
                    timeout=self._timeout,
                )
                retrieved_at = self._utc_now()
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_attempts:
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    "Binance USD-M ag hatasi; deneme %s/%s, %.2fs sonra tekrar: %s",
                    attempt,
                    self._max_attempts,
                    delay,
                    type(exc).__name__,
                )
                await self._sleep(delay)
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in self._RETRYABLE_STATUS or attempt >= self._max_attempts:
                    raise
                delay = self._retry_delay(exc.response, attempt)
                if delay is None:
                    raise
                logger.warning(
                    "Binance USD-M HTTP %s; deneme %s/%s, %.2fs sonra tekrar",
                    status,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                await self._sleep(delay)
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Binance USD-M yaniti JSON olarak parse edilemedi") from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Binance USD-M yaniti dict olmali; {type(payload).__name__} geldi"
                )
            return payload, retrieved_at

        raise RuntimeError("ulasilamaz: Binance retry dongusu sonuc uretmedi")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float | None:
        if response.status_code != 429:
            return self._backoff(attempt)
        raw = response.headers.get("Retry-After")
        if raw is None:
            # Binance 429 sonrası hızlı retry'ın IP banına dönüşebileceğini belirtir.
            # Kaynağın bekleme süresi bilinmiyorsa tahmin yürütme, çağırana geri dön.
            return None
        try:
            delay = float(raw)
        except ValueError:
            return None
        if not math.isfinite(delay) or delay < 0 or delay > self._max_retry_wait_seconds:
            return None
        return delay

    def _backoff(self, attempt: int) -> float:
        return min(self._retry_base_seconds * (2 ** (attempt - 1)), self._max_retry_wait_seconds)

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("provider clock timezone-aware UTC olmali")
        return value.astimezone(UTC)

    def _parse_mark_price(self, payload: dict[str, Any], retrieved_at: datetime) -> RawObservation:
        self._require_symbol(payload)
        event_time = self._millis(payload, "time")
        value = self._number(payload, "markPrice", minimum=0.0, minimum_inclusive=False)
        return RawObservation(
            timestamp_utc=event_time,
            retrieved_at_utc=retrieved_at,
            available_at_utc=max(retrieved_at, event_time),
            asset="BTC",
            venue="binance_futures",
            metric="mark_price",
            raw_value=value,
            unit="USDT/BTC",
            source_group=self.source_group,
            source_url=self._PREMIUM_URL,
            quality=1.0,
            notes="Binance USD-M public mark price",
        )

    def _parse_funding_rate(
        self, payload: dict[str, Any], retrieved_at: datetime
    ) -> RawObservation:
        self._require_symbol(payload)
        event_time = self._millis(payload, "time")
        next_funding = self._millis(payload, "nextFundingTime")
        if next_funding < event_time:
            raise ValueError("nextFundingTime response time oncesinde olamaz")
        value = self._number(payload, "lastFundingRate")
        return RawObservation(
            timestamp_utc=event_time,
            retrieved_at_utc=retrieved_at,
            available_at_utc=max(retrieved_at, event_time),
            asset="BTC",
            venue="binance_futures",
            metric="funding_rate",
            raw_value=value,
            unit="ratio",
            source_group=self.source_group,
            source_url=self._PREMIUM_URL,
            quality=1.0,
            notes=f"next_funding_at={next_funding.isoformat()}",
        )

    def _parse_open_interest(
        self, payload: dict[str, Any], retrieved_at: datetime
    ) -> RawObservation:
        self._require_symbol(payload)
        event_time = self._millis(payload, "time")
        value = self._number(payload, "openInterest", minimum=0.0, minimum_inclusive=True)
        return RawObservation(
            timestamp_utc=event_time,
            retrieved_at_utc=retrieved_at,
            available_at_utc=max(retrieved_at, event_time),
            asset="BTC",
            venue="binance_futures",
            metric="open_interest",
            raw_value=value,
            unit="BTC",
            source_group=self.source_group,
            source_url=self._OPEN_INTEREST_URL,
            quality=1.0,
            notes="Binance USD-M current open interest",
        )

    @staticmethod
    def _require_symbol(payload: dict[str, Any]) -> None:
        symbol = payload.get("symbol")
        if symbol != "BTCUSDT":
            raise ValueError(f"Binance USD-M symbol BTCUSDT olmali; gelen: {symbol!r}")

    @staticmethod
    def _millis(payload: dict[str, Any], field: str) -> datetime:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Binance USD-M {field} pozitif integer milisaniye olmali")
        try:
            return datetime.fromtimestamp(value / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(f"Binance USD-M {field} gecerli epoch milisaniye degil") from exc

    @staticmethod
    def _number(
        payload: dict[str, Any],
        field: str,
        *,
        minimum: float | None = None,
        minimum_inclusive: bool = True,
    ) -> float:
        raw = payload.get(field)
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ValueError(f"Binance USD-M {field} sayisal olmali; gelen: {raw!r}")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Binance USD-M {field} parse edilemedi: {raw!r}") from exc
        if not value.is_finite():
            raise ValueError(f"Binance USD-M {field} sonlu olmali; gelen: {raw!r}")
        if minimum is not None:
            bound = Decimal(str(minimum))
            invalid = value < bound if minimum_inclusive else value <= bound
            if invalid:
                operator = ">=" if minimum_inclusive else ">"
                raise ValueError(f"Binance USD-M {field} {operator} {minimum} olmali")
        return float(value)
