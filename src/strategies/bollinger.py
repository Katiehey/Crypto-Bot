import pandas as pd
import numpy as np
from enum import Enum
from src.regime.regime_detector import MarketRegime


class BollingerSignal(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class BollingerStrategy:
    def __init__(self, atr_stop_mult: float = 1.5):
        self.atr_stop_mult = atr_stop_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # --- Required columns (no enabled_strategies) ---
        required = ["close", "regime", "sentiment_norm",
                    "bb_mid_D", "bb_upper_D", "bb_lower_D", "atr_D"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        df["signal"] = BollingerSignal.FLAT.value
        df["stop_price"] = np.nan

        # --- Entry condition ---
        long_condition = (
            (df["regime"] == MarketRegime.RANGE.value)
            & (df["close"] > df["bb_upper_D"])
            & (df["sentiment_norm"] > 0.35)   # allow Fear (0.35–0.5), Greed, Extreme Greed
        )

        df.loc[long_condition, "signal"] = BollingerSignal.LONG.value
        df.loc[long_condition, "stop_price"] = df["close"] - df["atr_D"] * self.atr_stop_mult

        # --- Exit condition ---
        exit_condition = (
            (df["close"] < df["bb_mid_D"])      # price falls back below mid-band
            | (df["sentiment_norm"] <= 0.35)    # force exit in Neutral or Extreme Fear
        )
        df.loc[exit_condition, "signal"] = BollingerSignal.FLAT.value
        df.loc[exit_condition, "stop_price"] = np.nan

        # --- Persistence ---
        df["signal"] = (
            df["signal"].replace(BollingerSignal.FLAT.value, np.nan).ffill().fillna(BollingerSignal.FLAT.value)
        )
        df["stop_price"] = df["stop_price"].ffill()
        df.loc[df["signal"] == BollingerSignal.FLAT.value, "stop_price"] = np.nan

        # --- Final sentiment override ---
        df.loc[df["sentiment_norm"] <= 0.35, "signal"] = BollingerSignal.FLAT.value
        df.loc[df["sentiment_norm"] <= 0.35, "stop_price"] = np.nan

        return df[["signal", "stop_price", "bb_upper_D", "bb_lower_D", "bb_mid_D", "atr_D", "sentiment_norm"]]


if __name__ == "__main__":
    features_df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    strat = BollingerStrategy()
    signals = strat.generate_signals(features_df)

    print(signals.tail(20))
    print("\nSignal distribution:")
    print(signals["signal"].value_counts())

    print("\nSignals by sentiment bucket (refined):")
    sentiment_bins = pd.cut(
        signals["sentiment_norm"],
        bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
        labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = signals.groupby(sentiment_bins)["signal"].value_counts()
    print(diagnostic)
