"""Binance spot order-book spread and limited depth provider.

Source URL:
    https://api.binance.com/api/v3/depth

    Rate limits (2026-08-04 verified):
        Weight: 10 per request (limit=20).
            Spot bucket: 1200 weight/min IP limit.
                At 5-min collect cadence: 10 weight/5min = 2 weight/min — well within budget.

                Quirks:
                    - Response: {lastUpdateId, bids: [[price, qty],...], asks: [[price, qty],...]}.
                          Prices and quantities are strings — parse as float.
                              - limit=20 returns up to 20 levels on each side; sufficient for 1%-depth.
                                  - No timestamp in response — available_at = retrieved_at (snapshot semantics).
                                      - Depth historical backfill NOT available via Binance REST; only instantaneous.
                                          - bid_ask_spread_bps = (best_ask - best_bid) / mid * 10_000.
                                                Crossed book (bid >= ask) is transient; raise ValueError.
                                                    - depth_bid/ask_usd_1pct: USD value of levels within 1% of mid.
                                                    """

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from btc_radar.models.observation import RawObservation
from btc_radar.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_DEPTH_URL = "https://api.binance.com/api/v3/depth"
_SYMBOL = "BTCUSDT"
_LIMIT = 20
_DEPTH_PCT = 0.01

SOURCE_GROUP = "binance_depth"


class BinanceDepthProvider(BaseProvider):
      """Spot L2 spread and limited depth provider for BTCUSDT.

          Writes three RawObservation rows per call — all from the same
              atomic L2 snapshot and sharing the same available_at.

                  Metrics:
                          bid_ask_spread_bps  -- spread in basis points
                                  depth_bid_usd_1pct  -- total bid USD within 1% of mid
                                          depth_ask_usd_1pct  -- total ask USD within 1% of mid

                                              Examples
                                                  --------
                                                      >>> provider = BinanceDepthProvider()
                                                          >>> obs = await provider.fetch("bid_ask_spread_bps")
                                                              >>> obs[0].metric
                                                                  'bid_ask_spread_bps'

                                                                      >>> obs = await provider.fetch("all")
                                                                          >>> {o.metric for o in obs} == {
                                                                              ...     "bid_ask_spread_bps", "depth_bid_usd_1pct", "depth_ask_usd_1pct"
      ... }
          True
              """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
              self._client = http_client or httpx.AsyncClient(timeout=10.0)
              self._owns_client = http_client is None

    async def fetch(self, metric: str = "all", **kwargs: object) -> list[RawObservation]:
              """Fetch L2 spread and depth metrics.

                      Parameters
                              ----------
                                      metric:
                                                  One of bid_ask_spread_bps / depth_bid_usd_1pct /
                                                              depth_ask_usd_1pct / all.
                                                                      """
              logger.info("BinanceDepthProvider.fetch metric=%s", metric)

        retrieved_at = datetime.now(timezone.utc)
        response = await self._client.get(
                      _DEPTH_URL, params={"symbol": _SYMBOL, "limit": _LIMIT}
        )
        response.raise_for_status()
        data = response.json()

        bids: list[list[str]] = data["bids"]
        asks: list[list[str]] = data["asks"]

        if not bids or not asks:
                      raise ValueError("Empty order book — cannot compute spread or depth")

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])

        if best_bid <= 0 or best_ask <= 0:
                      raise ValueError(f"Non-positive best bid ({best_bid}) or ask ({best_ask})")
                  if best_bid >= best_ask:
                                raise ValueError(f"Crossed book: best_bid={best_bid} >= best_ask={best_ask}")

        mid = (best_bid + best_ask) / 2
        spread_bps = (best_ask - best_bid) / mid * 10_000
        lower_bound = mid * (1 - _DEPTH_PCT)
        upper_bound = mid * (1 + _DEPTH_PCT)

        depth_bid_usd = sum(
                      float(p) * float(q) for p, q in bids if float(p) >= lower_bound
        )
        depth_ask_usd = sum(
                      float(p) * float(q) for p, q in asks if float(p) <= upper_bound
        )

        available_at = retrieved_at
        base_kwargs = {
                      "asset": "BTC",
                      "venue": "binance",
                      "window": None,
                      "source_group": SOURCE_GROUP,
                      "source_url": _DEPTH_URL,
                      "quality": 0.90,
                      "notes": f"limit={_LIMIT} levels; depth band +-{_DEPTH_PCT * 100:.0f}pct of mid",
                      "retrieved_at_utc": retrieved_at,
                      "available_at_utc": available_at,
        }

        rows = [
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="bid_ask_spread_bps",
                                        raw_value=spread_bps,
                                        unit="bps",
                                        **base_kwargs,
                      ),
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="depth_bid_usd_1pct",
                                        raw_value=depth_bid_usd,
                                        unit="USD",
                                        **base_kwargs,
                      ),
                      RawObservation(
                                        timestamp_utc=retrieved_at,
                                        metric="depth_ask_usd_1pct",
                                        raw_value=depth_ask_usd,
                                        unit="USD",
                                        **base_kwargs,
                      ),
        ]

        if metric == "all":
                      return rows
                  matched = [r for r in rows if r.metric == metric]
        if not matched:
                      raise ValueError(
                                        f"Unknown metric {metric!r}; valid: "
                                        "bid_ask_spread_bps, depth_bid_usd_1pct, depth_ask_usd_1pct, all"
                      )
                  return matched

    async def aclose(self) -> None:
              if self._owns_client:
                            await self._client.aclose()
                
