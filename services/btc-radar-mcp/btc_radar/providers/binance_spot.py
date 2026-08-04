"""Public Binance spot BTCUSDT OHLCV and spot/perp basis provider.

Source URLs:
- https://api.binance.com/api/v3/klines (hourly OHLCV candles)
- https://api.binance.com/api/v3/ticker/price (live spot price, used for basis)

Rate limits (Binance docs, 2026-08-05): both endpoints are keyless single-symbol reads with
IP weight 2. This provider always sends ``symbol=BTCUSDT``.

Known quirks — verified live against the real API on 2026-08-05, not copied from docs:
- ``klines`` rows are oldest-first and the LAST row is frequently the still-forming candle:
  requesting ``limit=2, interval=1h`` returned a first row whose ``closeTime`` was already
  past and a second row whose ``closeTime`` was still ~8 minutes in the future. Using that
  row before it closes would be look-ahead into an hour that has not finished; any row whose
  ``closeTime`` is still in the future relative to the retrieval instant is dropped, and the
  newest remaining (fully closed) row is used.
- Each row is a fixed-position 12-element array, not a dict: ``[openTime, open, high, low,
  close, volume, closeTime, quoteVolume, tradeCount, takerBuyBaseVolume,
  takerBuyQuoteVolume, ignore]``. A row of a different length is a schema change, not a
  partial read, and is rejected fail-loud rather than guessed at.
- ``ticker/price`` returns no timestamp field at all (``{"symbol","price"}``); the
  observation time is necessarily the retrieval instant (the conservative default documented
  on ``RawObservation.available_at_utc``).
- Spot-perpetual basis is COMPUTED here, not fetched: ``(spot_price - perp_mark) /
  perp_mark × 100``. Both legs come from Binance itself (this provider's spot ticker plus
  ``BinanceFuturesProvider.fetch("mark_price")``), so — unlike the Coinbase/Korea premium
  tools planned in SPEC §2.3 — this is NOT a cross-exchange independence signal, it measures
  Binance's own spot-vs-perp gap. ``source_group`` is deliberately ``"derivatives"``, the
  same family as ``funding_stress``/``oi_buildup`` (ADR-0005): basis is a leverage/crowding
  observation, not a spot-demand one.
"""

from datetime import datetime
from typing import Any, ClassVar

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider
from btc_radar.providers.binance_futures import BinanceFuturesProvider
from btc_radar.providers.binance_http import BinancePublicClient

OHLCV_METRIC = "ohlcv_1h"
BASIS_METRIC = "spot_perp_basis"
_OHLCV_FIELD_UNITS: tuple[tuple[str, str, str], ...] = (
    ("spot_open", "open", "USDT/BTC"),
    ("spot_high", "high", "USDT/BTC"),
    ("spot_low", "low", "USDT/BTC"),
    ("spot_close", "close", "USDT/BTC"),
    ("spot_volume", "volume", "BTC"),
)
_KLINE_ROW_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
)
_MARK_PRICE_URL_FOR_NOTES = "https://fapi.binance.com/fapi/v1/premiumIndex"


class BinanceSpotProvider(BinancePublicClient, BaseProvider):
    """Normalize the public BTCUSDT spot hourly OHLCV candle and the spot/perp basis."""

    name: ClassVar[str] = "binance_spot"
    source_group: ClassVar[str] = "spot"
    supported_metrics: ClassVar[frozenset[str]] = frozenset({OHLCV_METRIC, BASIS_METRIC, "all"})

    _KLINES_URL = "https://api.binance.com/api/v3/klines"
    _TICKER_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"

    def __init__(
        self,
        *args: Any,
        futures_provider: BinanceFuturesProvider | None = None,
        **kwargs: Any,
    ) -> None:
        """``futures_provider`` is injectable so tests can mock the mark-price leg (DI).

        When omitted, this provider owns and closes its own ``BinanceFuturesProvider``.
        """
        super().__init__(*args, **kwargs)
        self._futures_provider = futures_provider
        self._owns_futures_provider = futures_provider is None

    async def aclose(self) -> None:
        await super().aclose()
        if self._owns_futures_provider and self._futures_provider is not None:
            await self._futures_provider.aclose()

    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Fetch the closed hourly OHLCV candle, the spot/perp basis, or both.

        Supported calls are ``fetch("ohlcv_1h")``, ``fetch("spot_perp_basis")`` and
        ``fetch("all")``. ``symbol`` may be omitted or set to the only supported value,
        ``BTCUSDT``.
        """
        self._validate_call(metric, params)
        if metric == OHLCV_METRIC:
            return await self._fetch_ohlcv()
        if metric == BASIS_METRIC:
            return [await self._fetch_basis()]
        return [*(await self._fetch_ohlcv()), await self._fetch_basis()]

    def _validate_call(self, metric: str, params: dict[str, Any]) -> None:
        if metric not in self.supported_metrics:
            allowed = ", ".join(sorted(self.supported_metrics))
            raise ValueError(f"desteklenmeyen Binance spot metrigi: {metric!r}; izinli: {allowed}")
        unknown = sorted(set(params) - {"symbol"})
        if unknown:
            raise ValueError(f"desteklenmeyen Binance spot parametreleri: {unknown}")
        symbol = params.get("symbol", "BTCUSDT")
        if symbol != "BTCUSDT":
            raise ValueError("bu provider yalniz BTCUSDT sembolunu destekler")

    async def _fetch_ohlcv(self) -> list[RawObservation]:
        payload, retrieved_at = await self._request_json(
            self._KLINES_URL, {"symbol": "BTCUSDT", "interval": "1h", "limit": 2}, expect=list
        )
        row = self._latest_closed_candle(payload, retrieved_at=retrieved_at)
        return self._parse_ohlcv_row(row, retrieved_at=retrieved_at)

    def _parse_ohlcv_row(
        self,
        row: dict[str, Any],
        *,
        retrieved_at: datetime,
        available_at: datetime | None = None,
    ) -> list[RawObservation]:
        """Normalize one validated kline row with explicit availability semantics."""
        open_time = self._millis(row, "open_time")
        close_time = self._millis(row, "close_time")
        effective_available_at = available_at or max(retrieved_at, close_time)
        notes = f"candle_open_at={open_time.isoformat()}; candle_close_at={close_time.isoformat()}"
        return [
            RawObservation(
                timestamp_utc=open_time,
                retrieved_at_utc=retrieved_at,
                available_at_utc=effective_available_at,
                asset="BTC",
                venue="binance_spot",
                metric=metric,
                raw_value=self._number(
                    row,
                    field,
                    minimum=0.0,
                    minimum_inclusive=field == "volume",
                ),
                unit=unit,
                window="1h",
                source_group=self.source_group,
                source_url=self._KLINES_URL,
                quality=1.0,
                notes=notes,
            )
            for metric, field, unit in _OHLCV_FIELD_UNITS
        ]

    def _latest_closed_candle(
        self, payload: list[Any], *, retrieved_at: datetime
    ) -> dict[str, Any]:
        if not payload:
            raise ValueError("Binance spot klines bos yanit dondu")
        rows = [self._kline_row_dict(row) for row in payload]
        closed = [row for row in rows if self._millis(row, "close_time") <= retrieved_at]
        if not closed:
            raise ValueError("Binance spot klines icinde kapanmis mum yok; en yeni satir hala acik")
        return closed[-1]

    @staticmethod
    def _kline_row_dict(row: Any) -> dict[str, Any]:
        if not isinstance(row, list) or len(row) != len(_KLINE_ROW_FIELDS):
            raise ValueError(
                f"Binance spot kline satiri {len(_KLINE_ROW_FIELDS)} alanli olmali: {row!r}"
            )
        return dict(zip(_KLINE_ROW_FIELDS, row, strict=True))

    async def _fetch_basis(self) -> RawObservation:
        spot_payload, spot_retrieved_at = await self._request_json(
            self._TICKER_PRICE_URL, {"symbol": "BTCUSDT"}, expect=dict
        )
        spot_symbol = spot_payload.get("symbol")
        if spot_symbol != "BTCUSDT":
            raise ValueError(f"Binance spot ticker symbol BTCUSDT olmali; gelen: {spot_symbol!r}")
        spot_price = self._number(spot_payload, "price", minimum=0.0, minimum_inclusive=False)

        if self._futures_provider is None:
            self._futures_provider = BinanceFuturesProvider()
        [mark] = await self._futures_provider.fetch("mark_price")

        retrieved_at = max(spot_retrieved_at, mark.retrieved_at_utc)
        event_time = max(spot_retrieved_at, mark.timestamp_utc)
        basis = (spot_price - mark.raw_value) / mark.raw_value * 100
        return RawObservation(
            timestamp_utc=event_time,
            retrieved_at_utc=retrieved_at,
            available_at_utc=max(retrieved_at, event_time),
            asset="BTC",
            venue="binance",
            metric=BASIS_METRIC,
            raw_value=basis,
            unit="%",
            source_group="derivatives",
            source_url=f"{self._TICKER_PRICE_URL} + {_MARK_PRICE_URL_FOR_NOTES}",
            quality=1.0,
            notes=(
                f"spot_price={spot_price}; perp_mark={mark.raw_value}; "
                "iki bacak da Binance, cross-exchange bagimsiz degil"
            ),
        )
