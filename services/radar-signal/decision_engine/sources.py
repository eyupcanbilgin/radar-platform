"""Fail-closed runtime adapters for closed Binance candles and decision context files."""

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

import ccxt

from decision_engine.features import LOOKBACK_BARS, Candle1h
from enricher.decision_context import DecisionContextV1, parse_decision_context

BINANCE_SYMBOL = "BTC/USDT:USDT"
BINANCE_TIMEFRAME = "1h"
BINANCE_SOURCE = "ccxt:binanceusdm:contract-price"


def require_utc_hour(value: datetime, *, field: str = "as_of_utc") -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} timezone-aware UTC olmalı")
    value = value.astimezone(UTC)
    if any((value.minute, value.second, value.microsecond)):
        raise ValueError(f"{field} kapanmış 1h mum sınırı olmalı")
    return value


def _brief_error(error: Exception) -> str:
    message = " ".join(str(error).split())[:240]
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


class OhlcvClient(Protocol):
    def fetch_time(self, params: dict | None = None) -> int | None: ...

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: int | None = None,
        limit: int | None = None,
        params: dict | None = None,
    ) -> list[list]: ...


class CandleSourceError(RuntimeError):
    """Base error returned by a public candle adapter."""


class CandleTransportError(CandleSourceError):
    """The public market endpoint could not be reached within the retry budget."""


class CandleDataError(CandleSourceError):
    """The endpoint returned malformed or contradictory OHLCV data."""


class CandleNotReadyError(RuntimeError):
    """The exchange clock says the requested candle has not passed its close grace yet."""


class ExchangeClockError(RuntimeError):
    """Exchange time could not safely establish which immutable slot is due."""


@dataclass(frozen=True)
class CandleBatch:
    candles: tuple[Candle1h, ...]
    source: str
    observed_at_utc: datetime
    exchange_time_utc: datetime
    requested_as_of_utc: datetime
    rows_received: int


class BinanceUsdMClosedCandleSource:
    """Read exact-window public BTCUSDT contract-price candles through pinned CCXT."""

    def __init__(
        self,
        client: OhlcvClient | None = None,
        *,
        max_attempts: int = 3,
        retry_delays: tuple[float, ...] = (1.0, 2.0),
        close_grace_seconds: int = 90,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts en az 1 olmalı")
        if len(retry_delays) < max_attempts - 1:
            raise ValueError("retry_delays her retry için değer taşımalı")
        if any(delay < 0 for delay in retry_delays):
            raise ValueError("retry gecikmesi negatif olamaz")
        if not 0 <= close_grace_seconds < 3600:
            raise ValueError("close_grace_seconds 0..3599 aralığında olmalı")
        self.client = client or ccxt.binanceusdm(
            {
                "enableRateLimit": True,
                "timeout": 10_000,
            }
        )
        self.max_attempts = max_attempts
        self.retry_delays = retry_delays
        self.close_grace_seconds = close_grace_seconds
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleeper = sleeper

    def _fetch_exchange_time_ms(self) -> int:
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw_time = self.client.fetch_time()
            except (ccxt.RateLimitExceeded, ccxt.DDoSProtection) as error:
                raise ExchangeClockError(
                    "Binance serverTime rate-limit/DDoS korumasına takıldı; retry yapılmadı: "
                    + _brief_error(error)
                ) from error
            except ccxt.NetworkError as error:
                if attempt == self.max_attempts:
                    raise ExchangeClockError(
                        f"Binance serverTime {attempt} denemede alınamadı: {_brief_error(error)}"
                    ) from error
                self.sleeper(self.retry_delays[attempt - 1])
                continue
            except ccxt.ExchangeError as error:
                raise ExchangeClockError(
                    "Binance serverTime kalıcı exchange hatası verdi: " + _brief_error(error)
                ) from error
            except Exception as error:
                raise ExchangeClockError(
                    "serverTime client beklenmeyen hata verdi: " + _brief_error(error)
                ) from error
            if isinstance(raw_time, bool) or not isinstance(raw_time, (int, float)):
                raise ExchangeClockError("Binance serverTime tam sayı epoch-ms olmalı")
            if not math.isfinite(float(raw_time)) or float(raw_time) != int(raw_time):
                raise ExchangeClockError("Binance serverTime sonlu tam sayı epoch-ms olmalı")
            return int(raw_time)
        raise AssertionError("ulaşılamaz serverTime retry durumu")

    def exchange_time(self) -> datetime:
        timestamp_ms = self._fetch_exchange_time_ms()
        try:
            return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
        except (OSError, OverflowError, ValueError) as error:
            raise ExchangeClockError(
                "Binance serverTime geçerli datetime aralığında değil"
            ) from error

    @staticmethod
    def _contains_target_open(rows: object, *, target_open_ms: int) -> bool:
        if not isinstance(rows, list):
            return False
        return any(
            isinstance(row, (list, tuple))
            and row
            and isinstance(row[0], (int, float))
            and not isinstance(row[0], bool)
            and float(row[0]) == target_open_ms
            for row in rows
        )

    def _fetch_rows(
        self,
        *,
        since_ms: int,
        until_ms: int,
        target_open_ms: int,
    ) -> list[list]:
        for attempt in range(1, self.max_attempts + 1):
            try:
                rows = self.client.fetch_ohlcv(
                    BINANCE_SYMBOL,
                    BINANCE_TIMEFRAME,
                    since=since_ms,
                    limit=LOOKBACK_BARS,
                    params={"until": until_ms},
                )
            except (ccxt.RateLimitExceeded, ccxt.DDoSProtection) as error:
                raise CandleTransportError(
                    "Binance rate-limit/DDoS koruması isteği reddetti; hızlı retry yapılmadı: "
                    + _brief_error(error)
                ) from error
            except ccxt.NetworkError as error:
                if attempt == self.max_attempts:
                    raise CandleTransportError(
                        f"Binance erişimi {attempt} denemede başarısız: {_brief_error(error)}"
                    ) from error
                self.sleeper(self.retry_delays[attempt - 1])
                continue
            except ccxt.ExchangeError as error:
                raise CandleTransportError(
                    "Binance kalıcı exchange hatası; retry yapılmadı: " + _brief_error(error)
                ) from error
            except Exception as error:
                raise CandleTransportError(
                    "OHLCV client beklenmeyen hata verdi; retry yapılmadı: " + _brief_error(error)
                ) from error
            if not isinstance(rows, list):
                raise CandleDataError("OHLCV cevabı liste olmalı")
            if self._contains_target_open(rows, target_open_ms=target_open_ms):
                return rows
            if attempt == self.max_attempts:
                return rows
            self.sleeper(self.retry_delays[attempt - 1])
        raise AssertionError("ulaşılamaz retry durumu")

    @staticmethod
    def _open_time(row: list, *, index: int) -> datetime:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise CandleDataError(f"OHLCV satırı en az 6 alan taşımalı: index={index}")
        raw_timestamp = row[0]
        if isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, (int, float)):
            raise CandleDataError(f"OHLCV timestamp sayısal epoch-ms olmalı: index={index}")
        if not math.isfinite(float(raw_timestamp)):
            raise CandleDataError(f"OHLCV timestamp sonlu epoch-ms olmalı: index={index}")
        try:
            timestamp_ms = int(raw_timestamp)
            open_time = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
        except (OSError, OverflowError, ValueError) as error:
            raise CandleDataError(f"OHLCV timestamp geçersiz: index={index}") from error
        if float(raw_timestamp) != timestamp_ms:
            raise CandleDataError(f"OHLCV timestamp tam sayı epoch-ms olmalı: index={index}")
        return open_time

    def fetch_closed(self, *, as_of_utc: datetime) -> CandleBatch:
        as_of_utc = require_utc_hour(as_of_utc)
        exchange_now = self.exchange_time()
        ready_at = as_of_utc + timedelta(seconds=self.close_grace_seconds)
        if exchange_now < ready_at:
            raise CandleNotReadyError(
                "Binance serverTime karar grace sınırına ulaşmadı: "
                f"server={exchange_now.isoformat()}, ready_at={ready_at.isoformat()}"
            )
        since = as_of_utc - timedelta(hours=LOOKBACK_BARS)
        since_ms = int(since.timestamp() * 1000)
        until_ms = int(as_of_utc.timestamp() * 1000) - 1
        target_open_ms = int((as_of_utc - timedelta(hours=1)).timestamp() * 1000)
        rows = self._fetch_rows(
            since_ms=since_ms,
            until_ms=until_ms,
            target_open_ms=target_open_ms,
        )
        candles: list[Candle1h] = []
        for index, row in enumerate(rows):
            open_time = self._open_time(row, index=index)
            try:
                require_utc_hour(open_time, field=f"ohlcv[{index}].open_time")
            except ValueError as error:
                raise CandleDataError(str(error)) from error
            close_time = open_time + timedelta(hours=1)
            if close_time > as_of_utc:
                continue
            try:
                candle = Candle1h(
                    open_time_utc=open_time,
                    close_time_utc=close_time,
                    # Logical exchange publication boundary. HTTP retrieval time is batch audit.
                    available_at_utc=close_time,
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                )
            except (TypeError, ValueError) as error:
                raise CandleDataError(
                    f"OHLCV satırı doğrulanamadı: index={index}, {_brief_error(error)}"
                ) from error
            candles.append(candle)

        candles.sort(key=lambda candle: candle.close_time_utc)
        closes = [candle.close_time_utc for candle in candles]
        if len(closes) != len(set(closes)):
            raise CandleDataError("OHLCV cevabında duplicate kapanış zamanı var")
        if any(candle.open_time_utc < since for candle in candles):
            raise CandleDataError("OHLCV cevabı istenen pencerenin öncesinde mum taşıyor")

        observed_at = self.clock()
        if observed_at.tzinfo is None:
            raise CandleDataError("provider clock timezone-aware olmalı")
        return CandleBatch(
            candles=tuple(candles),
            source=BINANCE_SOURCE,
            observed_at_utc=observed_at.astimezone(UTC),
            exchange_time_utc=exchange_now,
            requested_as_of_utc=as_of_utc,
            rows_received=len(rows),
        )


ContextStatus = Literal["ready", "missing", "invalid", "io_error"]


@dataclass(frozen=True)
class ContextRead:
    context: DecisionContextV1 | None
    status: ContextStatus
    path: Path
    error: str | None = None


class JsonDecisionContextSource:
    """Read one exact-hour decision-context/v1 artifact; never fall back to latest."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def path_for(self, *, as_of_utc: datetime) -> Path:
        as_of_utc = require_utc_hour(as_of_utc)
        return (
            self.root
            / "v1"
            / "BTCUSDT"
            / "1h"
            / f"{as_of_utc:%Y}"
            / f"{as_of_utc:%m}"
            / f"{as_of_utc:%d}"
            / f"{as_of_utc:%H}.json"
        )

    def read(self, *, as_of_utc: datetime) -> ContextRead:
        as_of_utc = require_utc_hour(as_of_utc)
        path = self.path_for(as_of_utc=as_of_utc)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ContextRead(context=None, status="missing", path=path)
        except UnicodeError as error:
            return ContextRead(
                context=None,
                status="invalid",
                path=path,
                error=_brief_error(error),
            )
        except OSError as error:
            return ContextRead(
                context=None,
                status="io_error",
                path=path,
                error=_brief_error(error),
            )

        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("context JSON kökü object olmalı")
            context = parse_decision_context(payload, expected_as_of=as_of_utc)
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError) as error:
            return ContextRead(
                context=None,
                status="invalid",
                path=path,
                error=_brief_error(error),
            )
        return ContextRead(context=context, status="ready", path=path)
