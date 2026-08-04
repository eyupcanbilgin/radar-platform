"""S-0002b — Hacim-Koşullu Intraday Momentum Stratejisi (Kart A Tam Sadakat).

Hipotez kartı: docs/hypotheses/S-0002b.md.
Akademik referans: Wen, Bouri, Xu ve Zhao (2022).

Kart A Kurallarına Tam Sadakat:
- Aynı UTC saatinin geçmiş dağılımı (groupby hour rolling rank/median)
- Giriş anından itibaren SABİT 1 ATR Stop Loss (Trailing YASAK; stop fiyatı sabit tutulur)
- Funding Oranı / Basis Aşırılık Filtresi (%5-%95 persentil dışı bloklanır)
- Dinamik Cüzdan Yüzdesi Sizing (%10 stake amount; sabit notional yasak)
- process_only_new_candles=True
- Global normalizasyon YASAK; yalnız rolling() pencereli
- Her giriş koşulu ayrı enter_tag taşıyor
"""

import sys
from datetime import datetime
from pathlib import Path

import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_absolute,
)
from pandas import DataFrame

# Boyutlandırma oranı config'den okunur (Ç6). Strateji dosyaları freqtrade tarafından
# user_data/strategies altından yüklendiği için servis kökü sys.path'e elle eklenir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from sizinglib import load_sizing, wallet_pct_stake  # noqa: E402

_SIZING = load_sizing()


class S0002bVolumeMomentum(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = True
    process_only_new_candles = True

    # 20 gün × 4 saatlik mum/saat = 80 aynı saat mum rolling penceresi
    startup_candle_count = 1920

    minimal_roi: dict = {}  # ROI çıkışı kapalı; çıkış = yapısal/zaman/custom_stoploss
    stoploss = -0.10  # Güvenlik ağı; asıl stop custom_stoploss'ta SABİT ATR-tabanlı
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

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Cüzdan yüzdesi sizing — oran `config/sizing.yaml`'dan gelir (Ç6, koda gömülmez).

        Sabit notional, cüzdan düşerken bahis oranını büyütür ve terminal getiriyi
        stratejinin değil sermaye tükenişinin ölçüsü hâline getirir (S-0002 vakası).
        """
        return wallet_pct_stake(self.wallets.get_total_stake_amount(), min_stake, _SIZING)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1. ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))

        # 2. Son 4 mumun (1 saat) toplam getirisi
        dataframe["return_4bar"] = dataframe["close"].pct_change(4)

        # 3. UTC Saat Dilimi Grubu (Kart A: "aynı saat diliminin dağılımı")
        dataframe["hour"] = dataframe["date"].dt.hour

        # Aynı UTC saatinin geçmiş rolling penceresindeki persentil sırası
        dataframe["return_4bar_pct_rank"] = dataframe.groupby("hour")["return_4bar"].transform(
            lambda x: x.rolling(80, min_periods=10).rank(pct=True)
        )

        # 4. Son 4 mumun toplam hacmi (1h volume) ve aynı UTC saatinin rolling medyanı
        dataframe["volume_1h"] = dataframe["volume"].rolling(4).sum()
        dataframe["volume_1h_median"] = dataframe.groupby("hour")["volume_1h"].transform(
            lambda x: x.rolling(80, min_periods=10).median()
        )

        # 5. Önceki 1 saatlik bar aralığı (shift(1) ile geleceğe sızıntı engellendi)
        dataframe["high_1h_max_shift1"] = dataframe["high"].shift(1).rolling(4).max()
        dataframe["low_1h_min_shift1"] = dataframe["low"].shift(1).rolling(4).min()

        # 6. Kart A 4. Koşulu: Funding Oranı Filtresi (%5 - %95 persentil aralığı)
        if "funding_rate" in dataframe.columns:
            dataframe["funding_rate_pct_rank"] = (
                dataframe["funding_rate"].rolling(1920, min_periods=96).rank(pct=True)
            )
            dataframe["funding_ok"] = (dataframe["funding_rate_pct_rank"] >= 0.05) & (
                dataframe["funding_rate_pct_rank"] <= 0.95
            )
        else:
            dataframe["funding_ok"] = True

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long giriş koşulları
        cond_long_return = dataframe["return_4bar_pct_rank"] >= float(self.return_percentile.value)
        cond_long_volume = dataframe["volume_1h"] >= (
            float(self.volume_mult.value) * dataframe["volume_1h_median"]
        )
        cond_long_breakout = dataframe["close"] > dataframe["high_1h_max_shift1"]
        cond_funding = dataframe["funding_ok"]

        # Short giriş koşulları
        cond_short_return = dataframe["return_4bar_pct_rank"] <= (
            1.0 - float(self.return_percentile.value)
        )
        cond_short_volume = dataframe["volume_1h"] >= (
            float(self.volume_mult.value) * dataframe["volume_1h_median"]
        )
        cond_short_breakout = dataframe["close"] < dataframe["low_1h_min_shift1"]

        dataframe.loc[
            cond_long_return & cond_long_volume & cond_long_breakout & cond_funding,
            ["enter_long", "enter_tag"],
        ] = (1, "mom_vol_breakout_long")

        dataframe.loc[
            cond_short_return & cond_short_volume & cond_short_breakout & cond_funding,
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
        """Giriş fiyatından SABİT 1 ATR stop loss (SABİT FİYAT — Trailing YASAK)."""
        # Eğer stop-loss zaten set edilmişse, sabit stop fiyatını KORU (None döndür).
        # Freqtrade None döndürüldüğünde mevcut stop fiyatını kesinlikle sıkılaştırmaz.
        if trade.stop_loss != self.stoploss:
            return None

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        atr = dataframe["atr"].iloc[-1]
        if atr != atr:  # NaN
            return None

        dist = float(atr) * float(self.atr_stop_mult.value)
        stop_price = trade.open_rate + dist if trade.is_short else trade.open_rate - dist

        return stoploss_from_absolute(
            stop_price, trade.open_rate, is_short=trade.is_short, leverage=trade.leverage
        )
