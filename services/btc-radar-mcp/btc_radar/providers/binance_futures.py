"""Public Binance USD-M futures current-snapshot provider.

Source URLs:
- https://fapi.binance.com/fapi/v1/premiumIndex (mark price + current funding rate)
- https://fapi.binance.com/fapi/v1/openInterest (current open interest)
- https://fapi.binance.com/fapi/v1/depth (order book spread + limited depth)

Rate limits (Binance docs, 2026-08-04): ``premiumIndex``/``openInterest`` have IP weight 1
when a single symbol is supplied.  ``depth`` weight depends on ``limit``; ``limit=20`` (used
here) is weight 5. This provider always sends ``symbol=BTCUSDT``; an all-symbol request is
intentionally impossible.

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
- ``depth`` responses carry no ``symbol`` field (verified live, 2026-08-05), so
  ``_require_symbol`` cannot be applied there; the request itself is always pinned to
  BTCUSDT. The event time is the ``E`` field (message output time), not ``T``
  (transaction time) — the two can differ by a few ms and ``E`` is what Binance
  documents as "when this book state was sent".
- Historical funding/OI backfills have different availability semantics and
  are deliberately outside this current-snapshot provider.
"""

from datetime import datetime
from typing import Any, ClassVar

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider
from btc_radar.providers.binance_http import BinancePublicClient


class BinanceFuturesProvider(BinancePublicClient, BaseProvider):
    """Normalize the public BTCUSDT USD-M mark, funding, OI, and order-book snapshot."""

    name: ClassVar[str] = "binance_futures"
    source_group: ClassVar[str] = "derivatives"
    supported_metrics: ClassVar[frozenset[str]] = frozenset(
        {"mark_price", "funding_rate", "open_interest", "order_book", "all"}
    )

    _PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
    _OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
    _DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
    #: Fixed page size, not a tunable threshold (CLAUDE.md kural 3 eşiklere değil, buna
    #: uygulanmaz — bu Binance'ın izin verdiği sabit bir sayfa boyutudur).
    _DEPTH_LIMIT = 20

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch one normalized metric or the deterministic three-metric bundle.

        Supported calls are ``fetch("mark_price")``, ``fetch("funding_rate")``,
        ``fetch("open_interest")``, ``fetch("order_book")`` and ``fetch("all")``
        (``all`` stays the original three-metric derivatives bundle; ``order_book``
        must be requested explicitly).  ``symbol`` may be omitted or set to the only
        supported value, ``BTCUSDT``.
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
        if metric == "order_book":
            payload, retrieved_at = await self._request_depth()
            return self._parse_order_book(payload, retrieved_at)

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

    async def _request_depth(self) -> tuple[dict[str, Any], datetime]:
        return await self._request_json(
            self._DEPTH_URL, {"symbol": "BTCUSDT", "limit": self._DEPTH_LIMIT}, expect=dict
        )

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

    def _parse_order_book(
        self, payload: dict[str, Any], retrieved_at: datetime
    ) -> list[RawObservation]:
        """Spread and limited depth from the top ``_DEPTH_LIMIT`` levels each side.

        Depth is reported as the summed notional of exactly the fetched levels, not an
        invented "within X% of mid" band — the page size is the only knob and it is a
        Binance-imposed constant (CLAUDE.md kural 3: eşikler config'den okunur; bu bir
        eşik değil, sabit bir sayfa boyutudur).
        """
        event_time = self._millis(payload, "E")
        bids = self._book_levels(payload, "bids")
        asks = self._book_levels(payload, "asks")
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        if best_ask <= best_bid:
            raise ValueError(
                f"Binance USD-M order book best_ask ({best_ask}) best_bid'den ({best_bid}) "
                "buyuk olmali"
            )
        mid = (best_bid + best_ask) / 2
        spread_bps = (best_ask - best_bid) / mid * 10_000
        depth_bid_usd = sum(price * qty for price, qty in bids)
        depth_ask_usd = sum(price * qty for price, qty in asks)
        available_at = max(retrieved_at, event_time)
        window = f"top_{len(bids)}x{len(asks)}"
        return [
            RawObservation(
                timestamp_utc=event_time,
                retrieved_at_utc=retrieved_at,
                available_at_utc=available_at,
                asset="BTC",
                venue="binance_futures",
                metric="order_book_spread_bps",
                raw_value=spread_bps,
                unit="bps",
                source_group="execution_context",
                source_url=self._DEPTH_URL,
                quality=1.0,
                notes=f"best_bid={best_bid}; best_ask={best_ask}",
            ),
            RawObservation(
                timestamp_utc=event_time,
                retrieved_at_utc=retrieved_at,
                available_at_utc=available_at,
                asset="BTC",
                venue="binance_futures",
                metric="order_book_depth_bid_usd",
                raw_value=depth_bid_usd,
                unit="USDT",
                window=window,
                source_group="execution_context",
                source_url=self._DEPTH_URL,
                quality=1.0,
                notes="Binance USD-M order book cekilen seviyelerin toplam bid notional'i",
            ),
            RawObservation(
                timestamp_utc=event_time,
                retrieved_at_utc=retrieved_at,
                available_at_utc=available_at,
                asset="BTC",
                venue="binance_futures",
                metric="order_book_depth_ask_usd",
                raw_value=depth_ask_usd,
                unit="USDT",
                window=window,
                source_group="execution_context",
                source_url=self._DEPTH_URL,
                quality=1.0,
                notes="Binance USD-M order book cekilen seviyelerin toplam ask notional'i",
            ),
        ]
