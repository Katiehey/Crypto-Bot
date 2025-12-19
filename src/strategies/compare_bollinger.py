import pandas as pd
from src.backtest.event_backtester import EventBacktester
from src.strategies.bollinger import BollingerStrategy as OriginalBollinger
from src.strategies.bollinger_refined import BollingerStrategy as RefinedBollinger

# Load features
df = pd.read_csv("data/btc_usdt_features.csv", index_col=0, parse_dates=True)

bt = EventBacktester(initial_capital=500)

# --- Original Bollinger ---
orig_strat = OriginalBollinger()
orig_signals = orig_strat.generate_signals(df)
orig_intent = orig_signals.rename(columns={"signal": "intent"})
orig_intent["source"] = "BOLLINGER_ORIGINAL"

orig_results = bt.run(df, orig_intent)
orig_summary = bt.summary(orig_results)

# --- Refined Bollinger ---
ref_strat = RefinedBollinger()
ref_signals = ref_strat.generate_signals(df)
ref_intent = ref_signals.rename(columns={"signal": "intent"})
ref_intent["source"] = "BOLLINGER_REFINED"

ref_results = bt.run(df, ref_intent)
ref_summary = bt.summary(ref_results)

print("\nOriginal Bollinger Summary:")
print(orig_summary)

print("\nRefined Bollinger Summary:")
print(ref_summary)
