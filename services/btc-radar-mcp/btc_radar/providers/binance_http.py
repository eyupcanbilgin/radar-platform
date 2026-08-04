"""Shared keyless HTTP core for public Binance USD-M endpoints.

Both the current-snapshot provider and the historical backfill provider talk to the same
host with the same retry budget, the same fail-loud number parsing and the same clock
discipline.  Keeping that logic in one place means a retry or parsing rule can never drift
between "what we collect live" and "what we backfill".

Known quirks that motivated this module:
- Every numeric field arrives as a string and must be parsed fail-loud (CLAUDE.md rule 2).
- Binance payload time can run slightly ahead of the local clock, so callers derive
  ``available_at`` from both the retrieval time and the exchange event time.
- A 429 without ``Retry-After`` is not guessable; Binance escalates fast retries to an IP
  ban, so the caller gets the error instead of an invented wait.
"""

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Self

import httpx

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


class BinancePublicClient:
    """Retry, parse and clock helpers for anonymous Binance market-data reads."""

    _HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "btc-radar/0.2 (public read-only market data)"
    }
    _RETRYABLE_STATUS: ClassVar[frozenset[int]] = frozenset({408, 429, 500, 502, 503, 504})

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

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close only a client created by this provider."""
        if self._owns_client:
            await self._client.aclose()

    async def _request_json(
        self,
        url: str,
        params: dict[str, Any],
        *,
        expect: type = dict,
    ) -> tuple[Any, datetime]:
        """Return the parsed payload plus the retrieval instant, or raise fail-loud."""
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
            if not isinstance(payload, expect):
                raise ValueError(
                    f"Binance USD-M yaniti {expect.__name__} olmali; {type(payload).__name__} geldi"
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
    def _book_levels(payload: dict[str, Any], field: str) -> list[tuple[float, float]]:
        """Parse an order-book side (``[[price_str, qty_str], ...]``) fail-loud."""
        raw = payload.get(field)
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"Binance USD-M {field} bos olmayan liste olmali")
        levels: list[tuple[float, float]] = []
        for entry in raw:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or not all(isinstance(v, str) for v in entry)
            ):
                raise ValueError(
                    f"Binance USD-M {field} seviyesi [fiyat, miktar] olmali: {entry!r}"
                )
            price_str, qty_str = entry
            try:
                price = Decimal(price_str)
                qty = Decimal(qty_str)
            except InvalidOperation as exc:
                raise ValueError(
                    f"Binance USD-M {field} seviyesi parse edilemedi: {entry!r}"
                ) from exc
            if not price.is_finite() or price <= 0:
                raise ValueError(f"Binance USD-M {field} fiyati sonlu ve > 0 olmali: {price_str!r}")
            if not qty.is_finite() or qty < 0:
                raise ValueError(f"Binance USD-M {field} miktari sonlu ve >= 0 olmali: {qty_str!r}")
            levels.append((float(price), float(qty)))
        return levels

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
