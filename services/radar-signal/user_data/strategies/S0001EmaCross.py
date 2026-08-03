"""S-0001 — EMA(20/50) kesişim + ATR stop: KONTROL/TABAN stratejisi.

Hipotez kartı: docs/hypotheses/S-0001.md. İyi olduğu için değil, kıyas için var
(SINYAL-SPEC §3.1): her gerçek aday bu tabanı ve buy&hold'u geçmek zorunda.

CLAUDE.md uyumu: process_only_new_candles=True (kural 2); global normalizasyon yok
(kural 3); tek zaman dilimi, üst TF merge yok (kural 4 tetiklenmez); 4 serbest
parametre (kural: ≤6) ve değerleri user_data/strategies/S0001EmaCross.json'da —
stratejide değil config'de (CLAUDE.md Teknoloji seti).
"""

import talib.abstract as ta
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_absolute,
)
from pandas import DataFrame


class S0001EmaCross(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 200  # en uzun pencere (EMA50) × ~4 ısınma payı

    minimal_roi: dict = {}  # ROI çıkışı kapalı; çıkış = ters kesişim + ATR stop
    stoploss = -0.10  # güvenlik ağı; asıl stop custom_stoploss'ta ATR-tabanlı
    use_custom_stoploss = True
    use_exit_signal = True

    ema_fast = IntParameter(10, 40, default=20, space="buy", optimize=False)
    ema_slow = IntParameter(30, 100, default=50, space="buy", optimize=False)
    atr_period = IntParameter(7, 28, default=14, space="sell", optimize=False)
    atr_stop_mult = DecimalParameter(1.0, 4.0, default=2.0, space="sell", optimize=False)

    def leverage(
        self,
        pair,
        current_time,
        current_rate,
        proposed_leverage,
        max_leverage,
        entry_tag,
        side,
        **kwargs,
    ) -> float:
        return 1.0  # kontrol stratejisi kaldıraçsız referans defter tutar

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=int(self.ema_fast.value))
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=int(self.ema_slow.value))
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cross_up = (dataframe["ema_fast"] > dataframe["ema_slow"]) & (
            dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1)
        )
        cross_down = (dataframe["ema_fast"] < dataframe["ema_slow"]) & (
            dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1)
        )
        dataframe.loc[cross_up, ["enter_long", "enter_tag"]] = (1, "ema_cross_up")
        dataframe.loc[cross_down, ["enter_short", "enter_tag"]] = (1, "ema_cross_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cross_down = (dataframe["ema_fast"] < dataframe["ema_slow"]) & (
            dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1)
        )
        cross_up = (dataframe["ema_fast"] > dataframe["ema_slow"]) & (
            dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1)
        )
        dataframe.loc[cross_down, ["exit_long", "exit_tag"]] = (1, "ema_cross_reverse")
        dataframe.loc[cross_up, ["exit_short", "exit_tag"]] = (1, "ema_cross_reverse")
        return dataframe

    def custom_stoploss(
        self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs
    ) -> float | None:
        """Chandelier tarzı ATR trailing stop.

        freqtrade stop'u yalnız lehte yönde sıkılaştırır; None dönüşü mevcut stop'u korur
        (ATR NaN ise güvenlik ağı -0.10 devrede kalır). Backtest'te dp.get_analyzed_dataframe
        simülasyon anına kadar kırpılmış döner — look-ahead yok.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        atr = dataframe["atr"].iloc[-1]
        if atr != atr:  # NaN
            return None
        dist = float(atr) * float(self.atr_stop_mult.value)
        stop_price = current_rate + dist if trade.is_short else current_rate - dist
        return stoploss_from_absolute(
            stop_price, current_rate, is_short=trade.is_short, leverage=trade.leverage
        )
