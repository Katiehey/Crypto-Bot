import pandas as pd
from datetime import timedelta
pd.set_option('future.no_silent_downcasting', True)

from src.backtest.event_backtester_refined import EventBacktester
from src.backtest.metrics import (
    calculate_cagr,
    calculate_drawdown,
    calculate_sharpe,
    trade_statistics,
)
from src.strategies.trend_following_refined import TrendFollowingStrategy
from src.strategies.mean_reversion_refined import MeanReversionStrategy
from src.engine.strategy_router_refined import StrategyRouter


class WalkForwardTester:
    def __init__(
        self,
        train_days: int = 365,
        test_days: int = 90,
        step_days: int = 90,
    ):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

        # instantiate strategies + router once
        self.trend_strategy = TrendFollowingStrategy()
        self.mr_strategy = MeanReversionStrategy()
        self.router = StrategyRouter()

    def run(self, df: pd.DataFrame):
        df = df.copy()
        df.index = pd.to_datetime(df.index)  # ensure datetime index
        results = []

        start = df.index.min()

        while True:
            train_start = start
            train_end = train_start + timedelta(days=self.train_days)
            test_end = train_end + timedelta(days=self.test_days)

            train_df = df.loc[train_start:train_end]
            test_df = df.loc[train_end:test_end]

            if len(test_df) < 50:
                break

            # --- Generate signals for test window ---
            trend_signals = self.trend_strategy.generate_signals(test_df)
            mr_signals = self.mr_strategy.generate_signals(test_df)
            boll_signals = pd.DataFrame({
                "signal": [None] * len(test_df),
                "stop_price": [None] * len(test_df),
            }, index=test_df.index)

            # --- Route intents ---
            intent_df = self.router.route(test_df, trend_signals, mr_signals, boll_signals)

            # --- Backtest using test data + intents ---
            bt = EventBacktester()
            equity = bt.run(test_df, intent_df)

            # Adjust depending on what bt.run() returns
            equity_curve = None
            if isinstance(equity, pd.DataFrame):
                if "equity" in equity.columns:
                    equity_curve = equity["equity"]
                elif "balance" in equity.columns:
                    equity_curve = equity["balance"]
                else:
                    equity_curve = equity.iloc[:, 0]
            elif isinstance(equity, pd.Series):
                equity_curve = equity
            elif isinstance(equity, dict) and "equity_curve" in equity:
                equity_curve = equity["equity_curve"]

            metrics = {
                "train_start": train_start,
                "train_end": train_end,
                "test_end": test_end,
                "cagr": calculate_cagr(equity_curve),
                "sharpe": calculate_sharpe(equity_curve),
                "max_drawdown": calculate_drawdown(equity_curve)["max_drawdown"].iloc[-1],
                **trade_statistics(equity),
            }

            results.append(metrics)
            start += timedelta(days=self.step_days)

        return pd.DataFrame(results).set_index("test_end")


# --- Temporary runner ---
if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    wf = WalkForwardTester()
    results = wf.run(df)

    print(results)
    print(results[["cagr", "sharpe", "max_drawdown"]].describe())
