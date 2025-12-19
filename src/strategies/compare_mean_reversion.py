import pandas as pd
from src.backtest.event_backtester import EventBacktester
from src.strategies.mean_reversion import MeanReversionStrategy  # original
from src.strategies.mean_reversion_refined import MeanReversionStrategy as RefinedMR  # refined

# Load features
df = pd.read_csv("data/btc_usdt_features.csv", index_col=0, parse_dates=True)

bt = EventBacktester(initial_capital=500)

# --- Original Mean Reversion ---
orig_strat = MeanReversionStrategy()
orig_signals = orig_strat.generate_signals(df)

# Adapt to backtester format
orig_intent = orig_signals.rename(columns={"signal": "intent"})
orig_intent["source"] = "MEAN_REVERSION"

orig_results = bt.run(df, orig_intent)
orig_summary = bt.summary(orig_results)

# --- Refined Mean Reversion ---
ref_strat = RefinedMR()
ref_signals = ref_strat.generate_signals(df)

# Adapt to backtester format
ref_intent = ref_signals.rename(columns={"signal": "intent"})
ref_intent["source"] = "MEAN_REVERSION_REFINED"

ref_results = bt.run(df, ref_intent)
ref_summary = bt.summary(ref_results)

print("\nOriginal Mean Reversion Summary:")
print(orig_summary)

print("\nRefined Mean Reversion Summary:")
print(ref_summary)
