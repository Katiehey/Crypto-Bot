import pandas as pd
from enum import Enum

from src.regime.regime_detector import MarketRegime
from src.strategies.trend_following import TrendSignal
from src.strategies.mean_reversion import MeanReversionSignal
from src.strategies.bollinger import BollingerSignal


class TradeIntent(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class StrategyRouter:
    def __init__(
        self,
        neutral_block: float = 0.35,   # Neutral upper bound
        fear_block: float = 0.25,      # Extreme Fear upper bound
    ):
        self.neutral_block = neutral_block
        self.fear_block = fear_block

    def route(
        self,
        df: pd.DataFrame,
        trend_signals: pd.DataFrame,
        mr_signals: pd.DataFrame,
        boll_signals: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Decide final trade intent based on regime and sentiment.
        Requires:
        - df['regime']
        - df['sentiment_norm']
        """

        result = pd.DataFrame(index=df.index)
        result["intent"] = TradeIntent.FLAT.value
        result["stop_price"] = None
        result["source"] = None

        for i in df.index:
            regime = df.loc[i, "regime"]
            sentiment = df.loc[i, "sentiment_norm"]

            # --- TREND REGIME ---
            if regime == MarketRegime.TREND.value:
                if sentiment is not None and sentiment <= 0.5:
                    continue  # Block TREND in Neutral, Fear, Extreme Fear
                if trend_signals.loc[i, "signal"] == TrendSignal.LONG.value:
                    result.loc[i, "intent"] = TradeIntent.LONG.value
                    result.loc[i, "stop_price"] = trend_signals.loc[i, "stop_price"]
                    result.loc[i, "source"] = "TREND"

            # --- RANGE REGIME ---
            elif regime == MarketRegime.RANGE.value:
                if sentiment is not None and sentiment <= self.neutral_block:
                    continue  # Block RANGE in Neutral and Extreme Fear
                if mr_signals.loc[i, "signal"] == MeanReversionSignal.LONG.value:
                    result.loc[i, "intent"] = TradeIntent.LONG.value
                    result.loc[i, "stop_price"] = mr_signals.loc[i, "stop_price"]
                    result.loc[i, "source"] = "MEAN_REVERSION"
                elif boll_signals.loc[i, "signal"] == BollingerSignal.LONG.value:
                    result.loc[i, "intent"] = TradeIntent.LONG.value
                    result.loc[i, "stop_price"] = boll_signals.loc[i, "stop_price"]
                    result.loc[i, "source"] = "BOLLINGER"

            # --- UNCERTAIN ---
            else:
                continue

        return result


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    from src.strategies.trend_following import TrendFollowingStrategy
    from src.strategies.mean_reversion import MeanReversionStrategy
    from src.strategies.bollinger import BollingerStrategy

    trend_strat = TrendFollowingStrategy()
    trend_signals = trend_strat.generate_signals(df)

    mr_strat = MeanReversionStrategy()
    mr_signals = mr_strat.generate_signals(df)

    boll_strat = BollingerStrategy()
    boll_signals = boll_strat.generate_signals(df)

    strat_router = StrategyRouter()
    routed = strat_router.route(df, trend_signals, mr_signals, boll_signals)

    print(routed.tail(20))
    print("\nFinal Intent distribution:")
    print(routed["intent"].value_counts())

    # --- Diagnostic: intents by sentiment bucket ---
    print("\nIntents by sentiment bucket:")
    sentiment_bins = pd.cut(
        df["sentiment_norm"],
        bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
        labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = routed.groupby(sentiment_bins)["intent"].value_counts()
    print(diagnostic)

    # --- Diagnostic: source strategy breakdown ---
    print("\nSource strategy breakdown:")
    source_counts = routed["source"].value_counts(dropna=False)
    print(source_counts)

    # --- Diagnostic: source by sentiment bucket ---
    print("\nSource by sentiment bucket:")
    source_by_sentiment = routed.groupby(sentiment_bins)["source"].value_counts()
    print(source_by_sentiment)
