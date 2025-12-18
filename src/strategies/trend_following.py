import pandas as pd
import numpy as np
from enum import Enum

from src.features.technical import sma, atr
from src.regime.regime_detector import MarketRegime


class TrendSignal(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class TrendFollowingStrategy:
    def __init__(
        self,
        sma_fast_window: int = 20,
        sma_slow_window: int = 50,
        atr_window: int = 14,
        atr_stop_mult: float = 2.0,
    ):
        self.sma_fast_window = sma_fast_window
        self.sma_slow_window = sma_slow_window
        self.atr_window = atr_window
        self.atr_stop_mult = atr_stop_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trend-following signals with sentiment filtering and exit logic.
        Requires 'regime' and 'sentiment_norm' columns in df.
        """

        df = df.copy()

        # --- Safety check ---
        required_cols = ["close", "regime", "sentiment_norm"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # --- Indicators ---
        df["sma_fast"] = sma(df["close"], self.sma_fast_window)
        df["sma_slow"] = sma(df["close"], self.sma_slow_window)
        df["atr"] = atr(df, self.atr_window)

        # --- Initialize ---
        df["signal"] = TrendSignal.FLAT.value
        df["stop_price"] = np.nan

        # --- Entry condition ---
        long_condition = (
            (df["sma_fast"] > df["sma_slow"])
            & (df["regime"] == MarketRegime.TREND.value)
            & (df["sentiment_norm"] > 0.5)  # only allow in Greed/Extreme Greed
        )

        df.loc[long_condition, "signal"] = TrendSignal.LONG.value
        df.loc[long_condition, "stop_price"] = (
            df["close"] - df["atr"] * self.atr_stop_mult
        )

        # --- Exit condition ---
        exit_condition = (
            (df["sma_fast"] < df["sma_slow"])
            | (df["sentiment_norm"] <= 0.5)  # sentiment drops out of Greed
        )
        df.loc[exit_condition, "signal"] = TrendSignal.FLAT.value
        df.loc[exit_condition, "stop_price"] = np.nan

        # --- Persist positions until exit ---
        df["signal"] = (
            df["signal"]
            .replace(TrendSignal.FLAT.value, np.nan)
            .ffill()
            .fillna(TrendSignal.FLAT.value)
        )

        # --- Sentiment override (force FLAT in Fear/Extreme Fear) ---
        df.loc[df["sentiment_norm"] <= 0.5, "signal"] = TrendSignal.FLAT.value
        df.loc[df["sentiment_norm"] <= 0.5, "stop_price"] = np.nan

        # --- Persist stop prices alongside signals ---
        df["stop_price"] = df["stop_price"].ffill()
        df.loc[df["signal"] == TrendSignal.FLAT.value, "stop_price"] = np.nan

        return df[
            ["signal", "stop_price", "sma_fast", "sma_slow", "atr", "sentiment_norm"]
        ]


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    strat = TrendFollowingStrategy()
    signals = strat.generate_signals(df)

    print(signals.tail(20))
    print("\nSignal distribution:")
    print(signals["signal"].value_counts())

    # --- Diagnostic: signals by sentiment bucket ---
    print("\nSignals by sentiment bucket (refined):")
    sentiment_bins = pd.cut(
        signals["sentiment_norm"],
        bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
        labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = signals.groupby(sentiment_bins)["signal"].value_counts()
    print(diagnostic)
