import pandas as pd
from enum import Enum
from datetime import datetime

from src.regime.regime_detector import MarketRegime
from src.strategies.trend_following_refined import TrendSignal


class TradeIntent(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class StrategyRouter:
    def __init__(self):
        # Fixed risk buckets for TREND only
        self.trend_risk_strict = 0.006
        self.trend_risk_loose = 0.003

    def route(
        self,
        df: pd.DataFrame,
        trend_signals: pd.DataFrame,
        mr_signals: pd.DataFrame = None,
        boll_signals: pd.DataFrame = None,
    ) -> pd.DataFrame:

        result = pd.DataFrame(index=df.index)
        result["intent"] = TradeIntent.FLAT.value
        result["stop_price"] = None
        result["source"] = None
        result["risk_per_trade"] = 0.0

        # --- Precompute indicators (cheap + deterministic) ---
        vol_ma20 = df["volume"].rolling(20).mean()
        price_ma50 = df["close"].rolling(50).mean()

        ema_fast = df["close"].ewm(span=20, adjust=False).mean()
        ema_slow = df["close"].ewm(span=50, adjust=False).mean()

        atr_ma20 = (
            df["atr_4h"].rolling(20).mean()
            if "atr_4h" in df.columns
            else None
        )

        for i in df.index:
            regime = df.loc[i, "regime"]
            sentiment = df.loc[i, "sentiment_norm"]

            # ====================================================
            # TREND STRATEGY (EXPECTANCY-OPTIMIZED)
            # ====================================================
            if regime == MarketRegime.TREND.value:

                # --- Sentiment gate: GREED only ---
                if sentiment is None or not (0.35 <= sentiment < 0.65):
                    continue

                # --- Signal gate ---
                if trend_signals.loc[i, "signal"] != TrendSignal.LONG.value:
                    continue

                # --- Breakout quality ---
                strict_pass = (
                    df.loc[i, "volume"] > vol_ma20.loc[i] * 1.2
                    and df.loc[i, "close"] >= price_ma50.loc[i]
                )

                if not strict_pass:
                    continue  # ❌ kill low-quality trades completely

                # --- Trend strength (EMA separation) ---
                trend_strength = (ema_fast.loc[i] - ema_slow.loc[i]) / ema_slow.loc[i]
                if trend_strength < 0.002:  # ~0.2% separation
                    continue

                # --- Volatility expansion ---
                if atr_ma20 is not None:
                    if df.loc[i, "atr_4h"] < atr_ma20.loc[i] * 1.1:
                        continue

                # --- Stop logic ---
                stop_price = trend_signals.loc[i, "stop_price"]

                if pd.isna(stop_price) or stop_price is None:
                    if "atr_4h" in df.columns and not pd.isna(df.loc[i, "atr_4h"]):
                        stop_price = df.loc[i, "close"] - 3 * df.loc[i, "atr_4h"]
                    else:
                        continue  # no valid stop → no trade

                # --- FINAL ENTRY ---
                result.loc[i, "intent"] = TradeIntent.LONG.value
                result.loc[i, "stop_price"] = stop_price
                result.loc[i, "source"] = "TREND"
                result.loc[i, "risk_per_trade"] = self.trend_risk_strict

        return result


# ============================================================
# Standalone execution
# ============================================================
if __name__ == "__main__":

    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    from src.strategies.trend_following_refined import TrendFollowingStrategy
    from src.backtest.event_backtester_refined import EventBacktester

    trend_strat = TrendFollowingStrategy()
    trend_signals = trend_strat.generate_signals(df)

    router = StrategyRouter()
    routed = router.route(df, trend_signals)

    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"data/final_intent_{timestamp}.csv"
    routed.to_csv(filename)

    print(f"\nSaved final intents to {filename}")
    print("\nFinal intent distribution:")
    print(routed["intent"].value_counts())
    print("\nSource breakdown:")
    print(routed["source"].value_counts(dropna=False))

    # --- Backtest ---
    bt = EventBacktester(initial_capital=500)
    results = bt.run(df, routed)

    print("\nLast 5 trades:")
    print(results.tail())

    print("\nPerformance Summary:")
    print(bt.summary(results))
