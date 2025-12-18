import pandas as pd
import numpy as np
from enum import Enum

from src.features.technical import rsi, atr, bollinger_bands
from src.regime.regime_detector import MarketRegime


class MeanReversionSignal(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class MeanReversionStrategy:
    def __init__(
        self,
        rsi_window: int = 14,
        rsi_entry: float = 30.0,
        rsi_exit: float = 50.0,
        bb_window: int = 20,
        bb_std: float = 2.0,
        atr_window: int = 14,
        atr_stop_mult: float = 1.5,
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
        Generate mean-reversion signals with sentiment filtering and exit logic.
        Requires 'regime' and 'sentiment_norm' columns in df.
        """

        df = df.copy()

        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["bb_mid"], df["bb_upper"], df["bb_lower"] = bollinger_bands(
            df["close"], self.bb_window, self.bb_std
        )
        df["atr"] = atr(df, self.atr_window)

        df["signal"] = MeanReversionSignal.FLAT.value
        df["stop_price"] = np.nan

        # --- Entry condition ---
        long_condition = (
            (df["regime"] == MarketRegime.RANGE.value)
            & (df["rsi"] < self.rsi_entry)
            & (df["close"] < df["bb_lower"])
            & (df["sentiment_norm"] > 0.35)   # only allow Fear (0.35–0.5), Greed, Extreme Greed
        )

        df.loc[long_condition, "signal"] = MeanReversionSignal.LONG.value
        df.loc[long_condition, "stop_price"] = (
            df["close"] - df["atr"] * self.atr_stop_mult
        )

        # --- Exit condition ---
        exit_condition = (
            (df["rsi"] > self.rsi_exit)
            | (df["close"] > df["bb_mid"])
            | (df["sentiment_norm"] <= 0.35)  # force exit in Neutral or Extreme Fear
        )
        df.loc[exit_condition, "signal"] = MeanReversionSignal.FLAT.value
        df.loc[exit_condition, "stop_price"] = np.nan

        # --- Persist positions until exit ---
        df["signal"] = (
            df["signal"]
            .replace(MeanReversionSignal.FLAT.value, np.nan)
            .ffill()
            .fillna(MeanReversionSignal.FLAT.value)
        )
        df["stop_price"] = df["stop_price"].ffill()
        df.loc[df["signal"] == MeanReversionSignal.FLAT.value, "stop_price"] = np.nan

        # --- Sentiment override (final safeguard) ---
        df.loc[df["sentiment_norm"] <= 0.35, "signal"] = MeanReversionSignal.FLAT.value
        df.loc[df["sentiment_norm"] <= 0.35, "stop_price"] = np.nan

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

    # --- Diagnostic: signals by sentiment bucket ---
    print("\nSignals by sentiment bucket:")
    sentiment_bins = pd.cut(
        signals["sentiment_norm"],
        bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
        labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = signals.groupby(sentiment_bins)["signal"].value_counts()
    print(diagnostic)
