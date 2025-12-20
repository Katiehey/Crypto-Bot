import time
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)

from src.execution.paper_broker import PaperBroker
from src.regime.regime_detector import RegimeDetector
from src.strategies.trend_following_refined import TrendFollowingStrategy
from src.strategies.mean_reversion_refined import MeanReversionStrategy
from src.engine.strategy_router_refined import StrategyRouter, TradeIntent
from src.risk.risk_manager import RiskManager, RiskConfig


class TradingBot:
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1d",
        sleep_seconds: int = 60 * 60 * 4,  # 4H
        force_extreme_greed: bool = False,  # NEW toggle
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.sleep_seconds = sleep_seconds
        self.force_extreme_greed = force_extreme_greed

        # Core components
        self.broker = PaperBroker()
        self.regime_detector = RegimeDetector()
        self.trend_strategy = TrendFollowingStrategy()
        self.mr_strategy = MeanReversionStrategy()
        self.router = StrategyRouter()

        self.position = None

    def run_once(self):
        print("Fetching market data...")
        df = self.broker.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
        #df.iloc[-1, df.columns.get_loc("volume")] = 5000  # force high volume


        # --- Regime Detection ---
        regime_df = self.regime_detector.detect(df)
        df = df.drop(columns=["trend_strength", "regime", "sentiment_norm"], errors="ignore")
        df = df.join(regime_df)

        # --- Sentiment ---
        if self.force_extreme_greed:
            df["sentiment_norm"] = 0.8   # Force Extreme Greed
            print("⚠️ Sentiment forced to Extreme Greed for testing")
        else:
            df["sentiment_norm"] = 0.5   # Neutral baseline

        # --- Strategy Signals ---
        trend_signals = self.trend_strategy.generate_signals(df)
        mr_signals = self.mr_strategy.generate_signals(df)
        boll_signals = pd.DataFrame({
            "signal": [None] * len(df),
            "stop_price": [None] * len(df),
        }, index=df.index)

        # --- Route Intent ---
        intent_df = self.router.route(df, trend_signals, mr_signals, boll_signals)

        latest = df.iloc[-1]
        latest_intent = intent_df.iloc[-1]

        print(f"Regime: {latest['regime']}")
        print(f"Intent: {latest_intent['intent']}")
        print("Balance:", self.broker.get_balance())

        print("Trend signal:", trend_signals.iloc[-1]["signal"])
        print("Volume:", latest["volume"], "vs avg:", df["volume"].rolling(20).mean().iloc[-1])

        # --- Position Handling ---
        balance = self.broker.get_balance()["USDT"]

        if self.position is None and latest_intent["intent"] == TradeIntent.LONG.value:
            entry_price = latest["close"]
            stop_price = latest_intent["stop_price"]

            risk_cfg = RiskConfig(
                risk_per_trade=latest_intent["risk_per_trade"],
                max_position_pct=0.25,
                min_trade_value=15.0
            )
            risk_mgr = RiskManager(risk_cfg)
            pos_info = risk_mgr.calculate_position_size(
                equity=balance,
                entry_price=entry_price,
                stop_price=stop_price,
            )
            print("RiskManager diagnostics:", pos_info)

            size = pos_info["size"]
            if size > 0:
                self.broker.place_order(
                    self.symbol,
                    side="buy",
                    amount=size,
                    price=entry_price,
                )
                self.position = {
                    "size": size,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                }
                print(f"Entered LONG: size={size}")
            else:
                print("Trade rejected. Reason:", pos_info["reason"])
                print("Entry:", entry_price, "Stop:", stop_price)


    def run(self):
        print("Starting trading bot (paper mode)...")
        while True:
            self.run_once()
            time.sleep(self.sleep_seconds)


import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the trading bot in paper mode")
    parser.add_argument(
        "--force-greed",
        action="store_true",
        help="Force sentiment to Extreme Greed (>=0.75) for testing trades",
    )
    args = parser.parse_args()

    bot = TradingBot(force_extreme_greed=args.force_greed)
    bot.run_once()  # run a single cycle for testing

