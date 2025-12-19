from src.backtest.event_backtester_refined import EventBacktester
from src.backtest.metrics import (
    calculate_cagr,
    calculate_calmar,
    calculate_drawdown,
    calculate_sharpe,
    calculate_sortino,
    trade_statistics,
)
import pandas as pd
import glob
import os

# Load backtest data
df = pd.read_csv(
    "data/btc_usdt_features.csv",
    index_col=0,
    parse_dates=True,
)

files = glob.glob("data/final_intent_*.csv")
if not files:
    raise FileNotFoundError("No final_intent files found in data/ directory.")

latest_file = max(files, key=os.path.getctime)
print(f"Loading latest intent file: {latest_file}")

intent = pd.read_csv(latest_file, index_col=0, parse_dates=True)

bt = EventBacktester(initial_capital=500)
trades = bt.run(df, intent)

# Equity curve
equity = trades["equity"]

# Metrics
metrics = {
    "CAGR": calculate_cagr(equity),
    "Sharpe": calculate_sharpe(equity),
    "Sortino": calculate_sortino(equity),
    "Calmar": calculate_calmar(equity),
    "Max Drawdown": calculate_drawdown(equity)["max_drawdown"].iloc[-1],
}

# Trade stats
trade_stats = trade_statistics(trades)

import numpy as np

def sharpe_by_bucket(trades: pd.DataFrame, risk_free_rate: float = 0.0) -> pd.Series:
    """Calculate Sharpe ratio per sentiment bucket."""
    sharpe_values = {}
    for bucket, group in trades.groupby("sentiment_bucket"):
        if group.empty:
            sharpe_values[bucket] = np.nan
            continue
        returns = group["pnl"] / group["equity"].shift(1)  # normalize pnl by equity
        returns = returns.dropna()
        if returns.std() == 0:
            sharpe_values[bucket] = 0.0
        else:
            excess = returns - risk_free_rate / 252
            sharpe_values[bucket] = np.sqrt(252) * excess.mean() / excess.std()
    return pd.Series(sharpe_values)

bucket_sharpes = sharpe_by_bucket(trades)
print("\nSharpe Ratio per Sentiment Bucket:")
print(bucket_sharpes)


print("Performance Metrics:", metrics)
print("Trade Statistics:", trade_stats)
