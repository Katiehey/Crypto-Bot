import pandas as pd
from enum import Enum

from src.features.technical import sma, atr


class MarketRegime(Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    UNCERTAIN = "UNCERTAIN"


class Strategy(Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    BOLLINGER = "BOLLINGER"


class RegimeDetector:
    def __init__(
        self,
        sma_fast_window: int = 20,
        sma_slow_window: int = 50,
        atr_window: int = 14,
        trend_threshold: float = 1.0,
        range_threshold: float = 0.5,
    ):
        self.sma_fast_window = sma_fast_window
        self.sma_slow_window = sma_slow_window
        self.atr_window = atr_window
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect market regime using historical data + sentiment filters.
        Returns dataframe with trend_strength, regime, and enabled_strategies columns.
        """

        df = df.copy()

        # --- Technical regime detection ---
        df["sma_fast"] = sma(df["close"], self.sma_fast_window)
        df["sma_slow"] = sma(df["close"], self.sma_slow_window)
        df["atr"] = atr(df, self.atr_window)

        df["trend_strength"] = (
            (df["sma_fast"] - df["sma_slow"]).abs() / df["atr"]
        )

        df["regime"] = MarketRegime.UNCERTAIN.value
        df.loc[df["trend_strength"] >= self.trend_threshold, "regime"] = MarketRegime.TREND.value
        df.loc[df["trend_strength"] <= self.range_threshold, "regime"] = MarketRegime.RANGE.value

        # --- Sentiment filter rules ---
        def map_strategies(sent):
            strategies = []
            if sent > 0.75:  # Extreme Greed
                strategies += [Strategy.TREND.value, Strategy.RANGE.value, Strategy.BOLLINGER.value]
            elif sent > 0.5:  # Greed
                strategies += [Strategy.TREND.value, Strategy.RANGE.value, Strategy.BOLLINGER.value]
            elif sent >= 0.25:  # Neutral / Fear
                strategies += [Strategy.RANGE.value, Strategy.BOLLINGER.value]
            else:  # Extreme Fear
                strategies = []  # UNCERTAIN only
            return strategies

        df["enabled_strategies"] = df["sentiment_norm"].apply(map_strategies)

        return df[["trend_strength", "regime", "enabled_strategies", "sentiment_norm"]]


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    detector = RegimeDetector()
    regimes = detector.detect(df)

    print(regimes.tail(20))
    print("\nRegime distribution:")
    print(regimes["regime"].value_counts())

    # --- Strategy summary by sentiment bucket ---
    print("\nEnabled strategies per sentiment bucket:")
    strategy_summary = (
        regimes.explode("enabled_strategies")
        .groupby(pd.cut(regimes["sentiment_norm"], bins=[0, 0.25, 0.5, 0.75, 1.0]))
        ["enabled_strategies"]
        .value_counts()
    )
    print(strategy_summary)
