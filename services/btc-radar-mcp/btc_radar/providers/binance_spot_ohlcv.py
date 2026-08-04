"""Public Binance spot OHLCV provider (closed 1h candle).

Source URLs:
    https://api.binance.com/api/v3/klines
    Docs: https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data

Rate limits (2026-08-04 verified):
    Weight: 2 per request (limit <= 99).
    Bucket: 1200 weight/min IP limit.
    At 5-min collect cadence: 2 weight/5min — well within budget.

Quirks:
    - Kline row index 0 = open_time (ms), 4 = close, 5 = volume (base asset),
      9 = taker_buy_base_volume. All prices are strings — parse carefully.
    - limit=2 returns [previous_closed, current_open]; index [0] is the safe
      closed candle. Do NOT use index [1]: it is still open.
    - close_time (index 6) is open_time + interval_ms - 1 ms. We set
      available_at = close_time + 1 ms so the candle is never used before it
      closes (ADR-0004 look-ahead rule).
    - symbol must be uppercase: BTCUSDT. Lowercase returns HTTP 400.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_KLINES_URL = "https://api.binance.com/api/v3/klines"
_SYMBOL = "BTCUSDT"
_INTERVAL = "1h"
_LIMIT = 2  # [closed_candle, current_open] — we use index 0 only


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


class BinanceSpotOhlcvProvider(BaseProvider):
    """Fetches the most recently closed 1h BTCUSDT spot candle from Binance.

    Returns one RawObservation per OHLCV field so downstream features can
    subscribe to individual metrics without parsing composite payloads.

    Examples
    --------
    >>> provider = BinanceSpotOhlcvProvider()
    >>> obs = await provider.fetch("spot_close")
    >>> obs[0].metric
    'spot_close'

    >>> obs = await provider.fetch("all")
    >>> {o.metric for o in obs} == {
    ...     "spot_open", "spot_high", "spot_low", "spot_close",
    ...     "spot_volume", "spot_taker_buy_volume"
    ... }
    True
    """

    SOURCE_GROUP = "binance_spot"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None

    async def fetch(self, metric: str = "all", **_kwargs: object) -> list[RawObservation]:
        """Fetch closed 1h candle metrics.

        Parameters
        ----------
        metric:
            One of spot_open / spot_high / spot_low / spot_close /
            spot_volume / spot_taker_buy_volume / all.
        """
        logger.info("BinanceSpotOhlcvProvider.fetch metric=%s", metric)
        params = {"symbol": _SYMBOL, "interval": _INTERVAL, "limit": _LIMIT}
        response = await self._client.get(_KLINES_URL, params=params)
        response.raise_for_status()
        rows = response.json()

        if len(rows) < 2:
            raise ValueError(
                f"Expected >=2 kline rows for closed-candle detection, got {len(rows)}"
            )

        # rows[0] = last closed candle
        row = rows[0]
        open_time_ms: int = int(row[0])
        close_time_ms: int = int(row[6])

        open_time = _ms_to_dt(open_time_ms)
        close_time = _ms_to_dt(close_time_ms)
        # available_at: 1 ms after the candle closes (ADR-0007 / ADR-0004)
        available_at = _ms_to_dt(close_time_ms + 1)
        retrieved_at = datetime.now(tz=timezone.utc)

        def _parse(raw: str) -> float:
            try:
                return float(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"BinanceSpotOhlcvProvider: cannot parse '{raw}' as float"
                ) from exc

        raw_values: dict[str, float] = {
            "spot_open": _parse(row[1]),
            "spot_high": _parse(row[2]),
            "spot_low": _parse(row[3]),
            "spot_close": _parse(row[4]),
            "spot_volume": _parse(row[5]),       # base asset (BTC)
            "spot_taker_buy_volume": _parse(row[9]),  # BTC bought by takers
        }

        metrics_to_return = (
            list(raw_values.keys()) if metric == "all" else [metric]
        )
        for m in metrics_to_return:
            if m not in raw_values:
                raise ValueError(
                    f"Unknown metric '{m}'. Valid: {list(raw_values)} or 'all'."
                )

        source_url = (
            f"{_KLINES_URL}?symbol={_SYMBOL}&interval={_INTERVAL}&limit={_LIMIT}"
        )
        return [
            RawObservation(
                timestamp_utc=open_time,
                retrieved_at_utc=retrieved_at,
                available_at_utc=available_at,
                asset="BTC",
                venue="binance_spot",
                metric=m,
                raw_value=raw_values[m],
                unit="USD" if m != "spot_volume" and m != "spot_taker_buy_volume" else "BTC",
                window="1h",
                source_group=self.SOURCE_GROUP,
                source_url=source_url,
                quality=1.0,
                notes=(
                    f"candle open={open_time.isoformat()} "
                    f"close={close_time.isoformat()} "
                    f"available_at={available_at.isoformat()}"
                ),
            )
            for m in metrics_to_return
        ]

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
