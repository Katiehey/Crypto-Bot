import pandas as pd
import numpy as np
from enum import Enum

from src.features.technical import rsi, atr, bollinger_bands
from src.regime.regime_detector import MarketRegime

# --- Candle pattern helpers ---
def is_hammer(row):
    body = abs(row["close"] - row["open"])
    candle_range = row["high"] - row["low"]
    lower_shadow = min(row["close"], row["open"]) - row["low"]
    upper_shadow = row["high"] - max(row["close"], row["open"])
    return (lower_shadow > 2 * body) and (upper_shadow < body) and (body / candle_range < 0.3)

def is_doji(row):
    body = abs(row["close"] - row["open"])
    candle_range = row["high"] - row["low"]
    return candle_range > 0 and (body / candle_range < 0.1)


class MeanReversionSignal(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class MeanReversionStrategy:
    def __init__(
        self,
        rsi_window: int = 14,
        rsi_entry: float = 25.0,   # stricter oversold threshold
        rsi_exit: float = 45.0,    # exit earlier
        bb_window: int = 20,
        bb_std: float = 2.0,
        atr_window: int = 14,
        atr_stop_mult: float = 2.0,  # wider stop to reduce whipsaws
    ):
        self.rsi_window = rsi_window
        self.rsi_entry = rsi_entry
        self.rsi_exit = rsi_exit
        self.bb_window = bb_window
        self.bb_std = bb_std
        self.atr_window = atr_window
        self.atr_stop_mult = atr_stop_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Mean-reversion signals with stricter sentiment filtering,
        candle confirmation, and trailing stop exits.
        """

        df = df.copy()

        # --- Indicators ---
        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["bb_mid"], df["bb_upper"], df["bb_lower"] = bollinger_bands(
            df["close"], self.bb_window, self.bb_std
        )
        df["atr"] = atr(df, self.atr_window)

        df["signal"] = MeanReversionSignal.FLAT.value
        df["stop_price"] = np.nan

        # --- Entry condition with candle confirmation ---
        long_condition = (
            (df["regime"] == MarketRegime.RANGE.value)
            & (df["rsi"] < 30)
            & (df["close"] < df["bb_lower"] * 1.01)
            & (df["sentiment_norm"] <= 0.35)   # only Greed & Extreme Greed
            #& (df.apply(is_hammer, axis=1) | df.apply(is_doji, axis=1))  # candle confirmation
        )

        df.loc[long_condition, "signal"] = MeanReversionSignal.LONG.value
        df.loc[long_condition, "stop_price"] = (
            df["close"] - df["atr"] * self.atr_stop_mult
        )

        # --- Exit condition (standard) ---
        exit_condition = (
            (df["rsi"] > self.rsi_exit)
            | (df["close"] > df["bb_mid"])
            
        )
        df.loc[exit_condition, "signal"] = MeanReversionSignal.FLAT.value
        df.loc[exit_condition, "stop_price"] = np.nan

        # --- Persistence ---
        df["signal"] = (
            df["signal"]
            .replace(MeanReversionSignal.FLAT.value, np.nan)
            .ffill()
            .fillna(MeanReversionSignal.FLAT.value)
        )
        df["stop_price"] = df["stop_price"].ffill()
        df.loc[df["signal"] == MeanReversionSignal.FLAT.value, "stop_price"] = np.nan

        # --- Sentiment override ---
        #df.loc[df["sentiment_norm"] <= 0.5, "signal"] = MeanReversionSignal.FLAT.value
        #df.loc[df["sentiment_norm"] <= 0.5, "stop_price"] = np.nan

        # --- Trailing stop update ---
        # If in LONG, trail stop behind close by ATR * multiplier
        trailing_stop = df["close"] - df["atr"] * self.atr_stop_mult
        df.loc[df["signal"] == MeanReversionSignal.LONG.value, "stop_price"] = np.maximum(
            df["stop_price"], trailing_stop
        )

        return df[
            ["signal", "stop_price", "rsi", "bb_upper", "bb_lower", "atr", "sentiment_norm"]
        ]


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    strat = MeanReversionStrategy()
    signals = strat.generate_signals(df)

    print(signals.tail(20))
    print("\nSignal distribution:")
    print(signals["signal"].value_counts())

    print("\nSignals by sentiment bucket:")
    sentiment_bins = pd.cut(
        signals["sentiment_norm"],
        bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
        labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = signals.groupby(sentiment_bins)["signal"].value_counts()
    print(diagnostic)
