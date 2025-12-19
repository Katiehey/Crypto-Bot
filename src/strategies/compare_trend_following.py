import pandas as pd
from src.backtest.event_backtester import EventBacktester
from src.strategies.trend_following import TrendFollowingStrategy  # original
from src.strategies.trend_following_refined import TrendFollowingStrategy as RefinedTrend  # refined

# Load features
df = pd.read_csv("data/btc_usdt_features.csv", index_col=0, parse_dates=True)

bt = EventBacktester(initial_capital=500)

# --- Original Trend Following ---
orig_strat = TrendFollowingStrategy()
orig_signals = orig_strat.generate_signals(df)

# Adapt to backtester format
orig_intent = orig_signals.rename(columns={"signal": "intent"})
orig_intent["source"] = "TREND_ORIGINAL"

orig_results = bt.run(df, orig_intent)
orig_summary = bt.summary(orig_results)

# --- Refined Trend Following ---
ref_strat = RefinedTrend()
ref_signals = ref_strat.generate_signals(df)

# Adapt to backtester format
ref_intent = ref_signals.rename(columns={"signal": "intent"})
ref_intent["source"] = "TREND_REFINED"

ref_results = bt.run(df, ref_intent)
ref_summary = bt.summary(ref_results)

print("\nOriginal Trend Following Summary:")
print(orig_summary)

print("\nRefined Trend Following Summary:")
print(ref_summary)
