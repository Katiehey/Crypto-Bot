import pandas as pd
from enum import Enum
from datetime import datetime

from src.regime.regime_detector import MarketRegime
from src.strategies.trend_following_refined import TrendSignal
from src.strategies.mean_reversion_refined import MeanReversionSignal, is_hammer, is_doji
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

        # --- Risk allocation per strategy ---
        self.risk_per_trade = {
            "TREND": 0.009,
            "MEAN_REVERSION": 0.006,
            "BOLLINGER": 0.001,
        }

        # --- Priority order for conflicts ---
        self.priority = {"TREND": 3, "MEAN_REVERSION": 2, "BOLLINGER": 1}

    def route(
        self,
        df: pd.DataFrame,
        trend_signals: pd.DataFrame,
        mr_signals: pd.DataFrame,
        boll_signals: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Decide final trade intent based on regime and sentiment.
        """

        result = pd.DataFrame(index=df.index)
        result["intent"] = TradeIntent.FLAT.value
        result["stop_price"] = None
        result["source"] = None
        result["risk_per_trade"] = 0.0

        for pos in range(len(df)):
            i = df.index[pos]
            regime = df.loc[i, "regime"]
            sentiment = df.loc[i, "sentiment_norm"]

            chosen_source = None
            chosen_stop = None

            # TREND regime: allow Greed and Extreme Greed
            if regime == MarketRegime.TREND.value:
                if sentiment is not None and sentiment >= 0.70:
                    if trend_signals.loc[i, "signal"] == TrendSignal.LONG.value:
                        if df.loc[i, "volume"] > df["volume"].rolling(20).mean().loc[i] * 1.2:
                            chosen_source = "TREND"
                            chosen_stop = trend_signals.loc[i, "stop_price"]

            # RANGE regime: allow MR in Extreme Fear, Bollinger in Neutral/Fear
            elif regime == MarketRegime.RANGE.value:
                candidates = []
                if sentiment is not None and sentiment <= 0.20:
                    if mr_signals.loc[i, "signal"] == MeanReversionSignal.LONG.value:
                        if is_hammer(df.loc[i]) or is_doji(df.loc[i]):
                            candidates.append(("MEAN_REVERSION", mr_signals.loc[i, "stop_price"]))
                if sentiment is not None and 0.55 <= sentiment < 0.65:
                    if boll_signals.loc[i, "signal"] == BollingerSignal.LONG.value:
                        candidates.append(("BOLLINGER", boll_signals.loc[i, "stop_price"]))

                if candidates:
                    candidates.sort(key=lambda x: self.priority[x[0]], reverse=True)
                    chosen_source, chosen_stop = candidates[0]

            # --- Apply chosen signal ---
            if chosen_source:
                result.loc[i, "intent"] = TradeIntent.LONG.value
                result.loc[i, "stop_price"] = chosen_stop
                result.loc[i, "source"] = chosen_source
                result.loc[i, "risk_per_trade"] = self.risk_per_trade[chosen_source]

                # Persist intent for next 2 bars by position
                for j in range(1, 3):
                    if pos + j < len(df):
                        next_idx = df.index[pos + j]
                        result.loc[next_idx, "intent"] = TradeIntent.LONG.value
                        result.loc[next_idx, "stop_price"] = chosen_stop
                        result.loc[next_idx, "source"] = chosen_source
                        result.loc[next_idx, "risk_per_trade"] = self.risk_per_trade[chosen_source]

        return result


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    from src.strategies.trend_following_refined import TrendFollowingStrategy
    from src.strategies.mean_reversion_refined import MeanReversionStrategy
    from src.strategies.bollinger import BollingerStrategy

    trend_strat = TrendFollowingStrategy()
    trend_signals = trend_strat.generate_signals(df)

    mr_strat = MeanReversionStrategy()
    mr_signals = mr_strat.generate_signals(df)

    boll_strat = BollingerStrategy()
    boll_signals = boll_strat.generate_signals(df)

    strat_router = StrategyRouter()
    routed = strat_router.route(df, trend_signals, mr_signals, boll_signals)

    # --- Save final routed intents for backtester ---
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"data/final_intent_{timestamp}.csv"
    routed.to_csv(filename)
    print(f"\nSaved final intents to {filename}")

    print(routed.tail(20))
    print("\nFinal Intent distribution:")
    print(routed["intent"].value_counts())

    print("\nSource strategy breakdown:")
    print(routed["source"].value_counts(dropna=False))

    # --- Trigger backtester ---
    from src.backtest.event_backtester_refined import EventBacktester

    def sentiment_bucket(val):
        if val <= 0.20:
            return "EXTREME_FEAR"
        elif val <= 0.35:
            return "FEAR/NEUTRAL"
        elif val <= 0.65:
            return "GREED"
        else:
            return "EXTREME_GREED"

    bt = EventBacktester(initial_capital=500)
    results = bt.run(df, routed)

    print("\nBacktest results (last 5 trades):")
    print(results.tail())
    print("Total trades:", len(results))

    summary = bt.summary(results)
    print("\nPerformance Summary by Strategy:")
    print(summary)

    print("\nSentiment diagnostics:")
    print("\nTrades per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["exit_type"].count())
    print("\nAverage PnL per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].mean())
    print("\nTotal PnL per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].sum())
    print("\nWin rate per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].apply(lambda x: (x > 0).mean()))
