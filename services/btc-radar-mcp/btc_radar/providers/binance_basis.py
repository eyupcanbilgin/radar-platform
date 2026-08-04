"""Binance spot/perp basis provider (anlık + tarihsel 1h).

Source URLs:
    Spot ticker:     https://api.binance.com/api/v3/ticker/price
        Spot klines:     https://api.binance.com/api/v3/klines
            Perp mark price: https://fapi.binance.com/fapi/v1/markPrice
                Index klines:    https://fapi.binance.com/futures/data/indexPriceKlines

                Rate limits (2026-08-04 verified):
                    /api/v3/ticker/price  : 2 weight/request
                        /api/v3/klines        : 2 weight/request
                            /fapi/v1/markPrice    : 1 weight/request
                                indexPriceKlines      : 1 weight/request
                                    Spot bucket: 1200 weight/min; Futures bucket: 2400 weight/min.
                                        At 5-min collect cadence: 6 weight total — well within budget.

                                        Quirks:
                                            - ticker/price returns {"symbol": "BTCUSDT", "price": "<str>"}; parse as float.
                                                - markPrice returns a list when symbol given; take index 0.
                                                    - basis_pct = (spot - mark) / mark * 100.
                                                          Negative = contango (perp > spot, typical long-funding pressure).
                                                                Positive = backwardation (spot > perp, rare).
                                                                    - indexPriceKlines: field order same as /api/v3/klines; close = index 4.
                                                                          available_at for historical = close_time + 1 ms (same rule as OHLCV).
                                                                              - symbol must be uppercase: BTCUSDT. Lowercase returns HTTP 400.
                                                                              """

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
_MARK_PRICE_URL = "https://fapi.binance.com/fapi/v1/markPrice"
_INDEX_KLINES_URL = "https://fapi.binance.com/futures/data/indexPriceKlines"
_SYMBOL = "BTCUSDT"
_INTERVAL = "1h"
_HIST_LIMIT = 500  # max per page for klines

SOURCE_GROUP = "binance_basis"


def _ms_to_dt(ms: int) -> datetime:
      return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class BinanceBasisProvider(BaseProvider):
      """Spot/perp basis provider for BTCUSDT.

          Fetches both spot price and perpetual mark price atomically, then
              computes basis_pct = (spot - mark) / mark * 100. Writes three
                  separate RawObservation rows so downstream features can access
                      raw prices independently.

                          Examples
                              --------
                                  >>> provider = BinanceBasisProvider()
                                      >>> obs = await provider.fetch("basis_pct")
                                          >>> obs[0].metric
                                              'basis_pct'

                                                  >>> obs = await provider.fetch("all")
                                                      >>> {o.metric for o in obs} == {"spot_price", "mark_price", "basis_pct"}
                                                          True

                                                              For historical 1h basis series:
                                                                  >>> obs = await provider.fetch("basis_pct_1h", limit=48)
                                                                      >>> len(obs) <= 48
                                                                          True
                                                                              """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
              self._client = http_client or httpx.AsyncClient(timeout=10.0)
              self._owns_client = http_client is None

    async def fetch(self, metric: str = "all", **kwargs: object) -> list[RawObservation]:
              """Fetch basis metrics.

                      Parameters
                              ----------
                                      metric:
                                                  One of spot_price / mark_price / basis_pct / all (anlık)
                                                              or basis_pct_1h / spot_price_1h / mark_price_1h (tarihsel 1h kapanmis).
                                                                      limit:
                                                                                  For *_1h metrics: number of closed hourly candles (default 48, max 500).
                                                                                          """
              logger.info("BinanceBasisProvider.fetch metric=%s", metric)

        if metric.endswith("_1h"):
                      return await self._fetch_historical(metric, int(kwargs.get("limit", 48)))
                  return await self._fetch_instant(metric)

    async def _fetch_instant(self, metric: str) -> list[RawObservation]:
              """Fetch spot price and mark price in parallel, compute basis."""
              retrieved_at = datetime.now(timezone.utc)

        # Fetch spot and perp concurrently
              spot_resp, mark_resp = await _gather(
                            self._client.get(_SPOT_TICKER_URL, params={"symbol": _SYMBOL}),
                            self._client.get(_MARK_PRICE_URL, params={"symbol": _SYMBOL}),
              )
        spot_resp.raise_for_status()
        mark_resp.raise_for_status()

        spot_data = spot_resp.json()
        mark_data = mark_resp.json()

        spot_price = float(spot_data["price"])
        # markPrice returns list or dict depending on whether symbol is given
        if isinstance(mark_data, list):
                      mark_price = float(mark_data[0]["markPrice"])
else:
              mark_price = float(mark_data["markPrice"])

        if mark_price == 0:
                      raise ValueError("mark_price is zero — cannot compute basis")

        basis_pct = (spot_price - mark_price) / mark_price * 100
        available_at = retrieved_at  # anlık snapshot

        base_kwargs = {
                      "asset": "BTC",
                      "venue": "binance",
                      "window": None,
                      "source_group": SOURCE_GROUP,
                      "source_url": _SPOT_TICKER_URL,
                      "quality": 0.95,
                      "notes": None,
                      "retrieved_at_utc": retrieved_at,
                      "available_at_utc": available_at,
        }

        rows = [
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="spot_price",
                                        raw_value=spot_price,
                                        unit="USD",
                                        **base_kwargs,
                      ),
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="mark_price",
                                        raw_value=mark_price,
                                        unit="USD",
                                        **base_kwargs,
                      ),
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="basis_pct",
                                        raw_value=basis_pct,
                                        unit="pct",
                                        **base_kwargs,
                      ),
        ]

        if metric == "all":
                      return rows
                  matched = [r for r in rows if r.metric == metric]
        if not matched:
                      raise ValueError(f"Unknown metric {metric!r}; valid: spot_price, mark_price, basis_pct, all")
                  return matched

    async def _fetch_historical(self, metric: str, limit: int) -> list[RawObservation]:
              """Fetch historical 1h closed-candle basis via index price klines.

                      Uses /api/v3/klines for spot and /futures/data/indexPriceKlines
                              for perp index price (proxy for mark). Pairs by close_time.
                                      available_at = close_time + 1 ms (ADR-0004 look-ahead rule).
                                              """
              limit = min(limit, _HIST_LIMIT)
              params = {"symbol": _SYMBOL, "interval": _INTERVAL, "limit": limit + 1}

        spot_resp, index_resp = await _gather(
                      self._client.get(_SPOT_KLINES_URL, params=params),
                      self._client.get(_INDEX_KLINES_URL, params=params),
        )
        spot_resp.raise_for_status()
        index_resp.raise_for_status()

        spot_rows = spot_resp.json()
        index_rows = index_resp.json()

        # Drop the last row (open candle) from both
        spot_closed = spot_rows[:-1] if len(spot_rows) > 1 else spot_rows
        index_closed = index_rows[:-1] if len(index_rows) > 1 else index_rows

        # Pair by close_time (index 6 for spot klines)
        spot_map = {row[6]: row for row in spot_closed}
        index_map = {row[6]: row for row in index_closed}
        common_closes = sorted(set(spot_map) & set(index_map))

        result: list[RawObservation] = []
        for close_ms in common_closes:
                      s = spot_map[close_ms]
                      ix = index_map[close_ms]

            spot_close = float(s[4])
            index_close = float(ix[4])

            if index_close == 0:
                              raise ValueError(f"index_close is zero at close_time={close_ms}")

            basis = (spot_close - index_close) / index_close * 100
            close_time = _ms_to_dt(close_ms)
            available_at = datetime.fromtimestamp((close_ms + 1) / 1000, tz=timezone.utc)
            retrieved_at = datetime.now(timezone.utc)

            base_kwargs = {
                              "asset": "BTC",
                              "venue": "binance",
                              "window": "1h",
                              "source_group": SOURCE_GROUP,
                              "source_url": _INDEX_KLINES_URL,
                              "quality": 0.90,
                              "notes": "historical: index price proxy for mark",
                              "retrieved_at_utc": retrieved_at,
                              "available_at_utc": available_at,
            }

            if metric in ("basis_pct_1h", "all"):
                              result.append(RawObservation(
                                                    timestamp_utc=close_time,
                                                    metric="basis_pct_1h",
                                                    raw_value=basis,
                                                    unit="pct",
                                                    **base_kwargs,
                              ))
                          if metric in ("spot_price_1h", "all"):
                                            result.append(RawObservation(
                                                                  timestamp_utc=close_time,
                                                                  metric="spot_price_1h",
                                                                  raw_value=spot_close,
                                                                  unit="USD",
                                                                  **base_kwargs,
                                            ))
                                        if metric in ("mark_price_1h", "all"):
                                                          result.append(RawObservation(
                                                                                timestamp_utc=close_time,
                                                                                metric="mark_price_1h",
                                                                                raw_value=index_close,
                                                                                unit="USD",
                                                                                **base_kwargs,
                                                          ))

        if not result:
                      raise ValueError(f"No overlapping candles for metric={metric!r}")
                  return result

    async def aclose(self) -> None:
              if self._owns_client:
                            await self._client.aclose()


async def _gather(
      *coros: object,
) -> tuple[httpx.Response, ...]:
    """Run multiple coroutines concurrently via asyncio.gather."""
    import asyncio
    return tuple(await asyncio.gather(*coros))  # type: ignore[arg-type]
