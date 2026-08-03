"""S-0002 — Hacim-Koşullu Intraday Momentum Stratejisi (Kart A).

Hipotez kartı: docs/hypotheses/S-0002.md.
Akademik referans: Wen, Bouri, Xu ve Zhao (2022).

CLAUDE.md ve CR-001/CR-002 uyumu:
- process_only_new_candles=True (CLAUDE.md kural 2)
- Global normalizasyon YASAK; yalnız rolling() pencereli (CLAUDE.md kural 3)
- Mutlak sayısal eşik YASAK; rolling persentil ve rolling medyan (Kart A şartı)
- Her giriş koşulu ayrı enter_tag taşıyor (gerekçe mekanizması)
- Serbest parametreler: ≤6 (5 adet: return_percentile, volume_mult, holding_candles,
  atr_period, atr_stop_mult)
"""

from datetime import datetime

import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_absolute,
)
from pandas import DataFrame


class S0002VolumeMomentum(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = True
    process_only_new_candles = True

    # 20 gün × 24 saat × 4 mum/saat = 1920 mum rolling pencere (freqtrade limitlerine uygun)
    LOOKBACK_WINDOW = 1920
    startup_candle_count = 1920

    minimal_roi: dict = {}  # ROI çıkışı kapalı; çıkış = yapısal/zaman/custom_stoploss
    stoploss = -0.10  # Güvenlik ağı; asıl stop custom_stoploss'ta ATR-tabanlı
    use_custom_stoploss = True
    use_exit_signal = True

    # Serbest parametreler (≤ 6 adet)
    return_percentile = DecimalParameter(0.70, 0.90, default=0.80, space="buy", optimize=False)
    volume_mult = DecimalParameter(1.10, 1.50, default=1.25, space="buy", optimize=False)
    holding_candles = IntParameter(2, 8, default=4, space="sell", optimize=False)
    atr_period = IntParameter(7, 28, default=14, space="sell", optimize=False)
    atr_stop_mult = DecimalParameter(0.5, 2.5, default=1.0, space="sell", optimize=False)

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0  # Referans defter kaldıraçsız tutulur

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1. ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))

        # 2. Son 4 mumun (1 saat) toplam getirisi
        dataframe["return_4bar"] = dataframe["close"].pct_change(4)

        # 3. Son 4 mum getirisinin rolling persentil sırası (Look-ahead yok,
        # global normalizasyon yok)
        dataframe["return_4bar_pct_rank"] = dataframe["return_4bar"].rolling(
            window=self.LOOKBACK_WINDOW, min_periods=960
        ).rank(pct=True)

        # 4. Son 4 mumun toplam hacmi (1h volume) ve rolling medyanı
        dataframe["volume_1h"] = dataframe["volume"].rolling(4).sum()
        dataframe["volume_1h_median"] = dataframe["volume_1h"].rolling(
            window=self.LOOKBACK_WINDOW, min_periods=960
        ).median()

        # 5. Önceki 1 saatlik bar aralığı (shift(1) ile geleceğe sızıntı engellendi)
        dataframe["high_1h_max_shift1"] = dataframe["high"].shift(1).rolling(4).max()
        dataframe["low_1h_min_shift1"] = dataframe["low"].shift(1).rolling(4).min()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long giriş koşulları
        cond_long_return = dataframe["return_4bar_pct_rank"] >= float(self.return_percentile.value)
        cond_long_volume = dataframe["volume_1h"] >= (
            float(self.volume_mult.value) * dataframe["volume_1h_median"]
        )
        cond_long_breakout = dataframe["close"] > dataframe["high_1h_max_shift1"]

        # Short giriş koşulları
        cond_short_return = dataframe["return_4bar_pct_rank"] <= (
            1.0 - float(self.return_percentile.value)
        )
        cond_short_volume = dataframe["volume_1h"] >= (
            float(self.volume_mult.value) * dataframe["volume_1h_median"]
        )
        cond_short_breakout = dataframe["close"] < dataframe["low_1h_min_shift1"]

        dataframe.loc[
            cond_long_return & cond_long_volume & cond_long_breakout,
            ["enter_long", "enter_tag"],
        ] = (1, "mom_vol_breakout_long")

        dataframe.loc[
            cond_short_return & cond_short_volume & cond_short_breakout,
            ["enter_short", "enter_tag"],
        ] = (1, "mom_vol_breakout_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Yapısal çıkış: Long için son 2 mum düşüğünün altına inilmesi, Short için yüksek aşılması
        exit_long_struct = dataframe["close"] < dataframe["low"].shift(1).rolling(2).min()
        exit_short_struct = dataframe["close"] > dataframe["high"].shift(1).rolling(2).max()

        dataframe.loc[exit_long_struct, ["exit_long", "exit_tag"]] = (1, "low_2bar_break")
        dataframe.loc[exit_short_struct, ["exit_short", "exit_tag"]] = (1, "high_2bar_break")

        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        """Zaman tabanlı çıkış: Pozisyon 4 mumu (1 saat) doldurduğunda çık."""
        open_time = trade.open_date_utc
        duration_seconds = (current_time - open_time).total_seconds()
        max_duration_seconds = int(self.holding_candles.value) * 15 * 60

        if duration_seconds >= max_duration_seconds:
            return "time_exit"
        return None

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        """Chandelier tarzı ATR trailing stop."""
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
