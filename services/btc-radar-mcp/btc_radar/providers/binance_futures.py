"""Public Binance USD-M futures current-snapshot provider.

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
- ``lastFundingRate`` is the RUNNING rate for the open funding period, not a settled
  payment.  The settled 8h series lives in ``binance_futures_history`` under the
  separate ``funding_rate_settled`` metric; mixing the two into one series would
  compute percentiles over a mixture of forecasts and settlements.
- Binance payload time can be slightly ahead of the local clock.  To prevent a
  future observation leaking through the PIT store, ``available_at`` is the
  later of response retrieval time and exchange event time.
- Historical funding/OI backfills have different availability semantics and
  are deliberately outside this current-snapshot provider.
"""

from datetime import datetime
from typing import Any, ClassVar

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider
from btc_radar.providers.binance_http import BinancePublicClient


class BinanceFuturesProvider(BinancePublicClient, BaseProvider):
    """Normalize the public BTCUSDT USD-M mark, funding, and OI snapshot."""

    name: ClassVar[str] = "binance_futures"
    source_group: ClassVar[str] = "derivatives"
    supported_metrics: ClassVar[frozenset[str]] = frozenset(
        {"mark_price", "funding_rate", "open_interest", "all"}
    )

    _PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
    _OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch one normalized metric or the deterministic three-metric bundle.

        Supported calls are ``fetch("mark_price")``, ``fetch("funding_rate")``,
        ``fetch("open_interest")`` and ``fetch("all")``.  ``symbol`` may be
        omitted or set to the only supported value, ``BTCUSDT``.
        """
        self._validate_call(metric, params)
        if metric == "all":
            premium, retrieved_premium = await self._request_premium()
            oi, retrieved_oi = await self._request_open_interest()
            return [
                self._parse_mark_price(premium, retrieved_premium),
                self._parse_funding_rate(premium, retrieved_premium),
                self._parse_open_interest(oi, retrieved_oi),
            ]
        if metric == "mark_price":
            payload, retrieved_at = await self._request_premium()
            return [self._parse_mark_price(payload, retrieved_at)]
        if metric == "funding_rate":
            payload, retrieved_at = await self._request_premium()
            return [self._parse_funding_rate(payload, retrieved_at)]

        payload, retrieved_at = await self._request_open_interest()
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

    async def _request_premium(self) -> tuple[dict[str, Any], datetime]:
        return await self._request_json(self._PREMIUM_URL, {"symbol": "BTCUSDT"}, expect=dict)

    async def _request_open_interest(self) -> tuple[dict[str, Any], datetime]:
        return await self._request_json(self._OPEN_INTEREST_URL, {"symbol": "BTCUSDT"}, expect=dict)

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
