import itertools
import pandas as pd
import glob
import os

from src.backtest.event_backtester_refined import EventBacktester
from src.backtest.metrics import calculate_cagr, calculate_drawdown, calculate_sharpe, trade_statistics


class RobustnessTester:
    def __init__(self, param_grid: dict, intent: pd.DataFrame):
        self.param_grid = param_grid
        self.intent = intent

    def run(self, df: pd.DataFrame):
        records = []

        keys = self.param_grid.keys()
        values = self.param_grid.values()

        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))

            bt = EventBacktester(
                initial_capital=params.get("initial_capital", 500.0),
                risk_per_trade=params.get("risk_per_trade", 0.003),
                slippage=params.get("slippage", 0.0003),
                fee=params.get("fee", 0.0004),
            )

            results = bt.run(df, self.intent)

            #stats = trade_statistics(results["trades"])
            stats = trade_statistics(results)

            # Separate trades by regime
            if "regime" in results.columns:
                trend_trades = results[results["regime"] == "TREND"]
                range_trades = results[results["regime"] == "RANGE"]

                trend_stats = trade_statistics(trend_trades)
                range_stats = trade_statistics(range_trades)
            else:
                trend_stats, range_stats = {}, {}
                trend_stats, range_stats = {}, {}


            records.append(
                {
                    **params,
                    "cagr": calculate_cagr(results["equity"]),
                    "max_dd": calculate_drawdown(results["equity"])["max_drawdown"].iloc[-1],
                    "sharpe": calculate_sharpe(results["equity"]),
                    "expectancy": stats.get("expectancy", 0.0),
                    "win_rate": stats.get("win_rate", 0.0),
                    "avg_win": stats.get("avg_win", 0.0),
                    "avg_loss": stats.get("avg_loss", 0.0),
                    "total_trades": stats.get("total_trades", 0),
                    "trend_expectancy": trend_stats.get("expectancy", 0.0),
                    "range_expectancy": range_stats.get("expectancy", 0.0),
                }
            )

        return pd.DataFrame(records)


# Example parameter grid aligned with your system
param_grid = {
    "initial_capital": [500, 1000],
    "risk_per_trade": [0.003, 0.005, 0.01],
    "slippage": [0.0002, 0.0003],
    "fee": [0.0003, 0.0004],
}


from src.backtest.robustness import RobustnessTester

if __name__ == "__main__":
    # --- Load feature data ---
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    # --- Load latest intent file ---
    files = glob.glob("data/final_intent_*.csv")
    if not files:
        raise FileNotFoundError("No final_intent files found in data/ directory.")

    latest_file = max(files, key=os.path.getctime)
    print(f"Loading latest intent file: {latest_file}")

    intent = pd.read_csv(latest_file, index_col=0, parse_dates=True)

    # --- Define parameter grid ---
    param_grid = {
        "initial_capital": [500, 1000],
        "risk_per_trade": [0.003, 0.005, 0.01],
        "slippage": [0.0002, 0.0003],
        "fee": [0.0003, 0.0004],
    }

    # --- Run robustness test ---
    tester = RobustnessTester(param_grid, intent)
    robustness_results = tester.run(df)

    print("\nRobustness test results:")
    print(robustness_results.describe())
    print(robustness_results[["risk_per_trade", "trend_expectancy", "range_expectancy"]])
    print(robustness_results.head())
    print(robustness_results.columns)

    import matplotlib.pyplot as plt

    
    # --- Run a single backtest to get raw trades ---
    bt = EventBacktester(initial_capital=500)
    trade_results = bt.run(df, intent)    # <-- this has exit_type, pnl, etc.

    trade_results = trade_results.sort_values("timestamp")

    print("Trade results columns:", trade_results.columns)
    print(trade_results.head())
    summary = bt.summary(trade_results)
    print(summary)

    window = 100

    def calc_expectancy(window_df):
        wins = window_df[window_df["pnl"] > 0]["pnl"]
        losses = window_df[window_df["pnl"] < 0]["pnl"]
        win_rate = len(wins) / len(window_df) if len(window_df) > 0 else 0
        loss_rate = len(losses) / len(window_df) if len(window_df) > 0 else 0
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        return (win_rate * avg_win) + (loss_rate * avg_loss)

    # Rolling expectancy
    rolling_expectancy = trade_results["pnl"].rolling(window).apply(
        lambda x: calc_expectancy(trade_results.loc[x.index]), raw=False
    )

    required_cols = ["pnl", "drawdown", "source", "sentiment_bucket"]
    for col in required_cols:
        if col not in trade_results.columns:
            if col == "source":
                trade_results[col] = "UNKNOWN"
            elif col == "sentiment_bucket":
                trade_results[col] = "UNKNOWN"
            else:
                trade_results[col] = 0.0

    if "pnl" in trade_results.columns and "sentiment_bucket" in trade_results.columns:
        sentiment_groups = trade_results.groupby("sentiment_bucket")

        avg_win = sentiment_groups.apply(lambda g: g[g["pnl"] > 0]["pnl"].mean()).fillna(0)
        avg_loss = sentiment_groups.apply(lambda g: g[g["pnl"] < 0]["pnl"].mean()).fillna(0)

        print("Avg win per sentiment:", avg_win)
        print("Avg loss per sentiment:", avg_loss)
        print("PnL value counts:", trade_results["pnl"].value_counts())
        print("Number of trades:", len(trade_results[trade_results["exit_type"].isin(["STOP","SIGNAL","PARTIAL_1.0R","PARTIAL_2.0R","PARTIAL_3.0R"]) ]))

        plt.figure(figsize=(12,6))
        plt.plot(trade_results["timestamp"], rolling_expectancy, label="Rolling Expectancy (100 trades)")
        plt.axhline(0, color="red", linestyle="--")
        plt.title("Rolling Expectancy Over Time")
        plt.ylabel("Expectancy")
        plt.xlabel("Time")
        plt.legend()
        plt.show()
        
        trade_counts = trade_results.groupby("sentiment_bucket")["exit_type"].count()
        trade_counts.plot(kind="bar", title="Trade count per sentiment bucket")
        plt.show()


        plt.bar(avg_win.index, avg_win.values, color="green", label="Avg Win")
        plt.bar(avg_loss.index, avg_loss.values, color="red", label="Avg Loss")
        plt.title("Average Win vs Loss per Sentiment Bucket")
        plt.ylabel("PnL")
        plt.legend()
        plt.show()
    else:
        print("PnL or sentiment_bucket column missing in results; skipping sentiment analysis plot.")   

