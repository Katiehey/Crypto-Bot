import pandas as pd
from src.risk.risk_manager import RiskManager, RiskConfig

rm = RiskManager(RiskConfig())

# Define test cases with varying stop distances
test_cases = [
    {"equity": 500, "entry_price": 50_000, "stop_price": 48_000, "label": "Wide stop (2000 gap)"},
    {"equity": 500, "entry_price": 50_000, "stop_price": 49_500, "label": "Medium stop (500 gap)"},
    {"equity": 500, "entry_price": 50_000, "stop_price": 49_900, "label": "Tight stop (100 gap)"},
    {"equity": 500, "entry_price": 50_000, "stop_price": 51_000, "label": "Invalid stop (above entry)"},
    {"equity": 500, "entry_price": 50_000, "stop_price": 49_999.5, "label": "Tiny stop (below min trade value)"},
]

results = []

for case in test_cases:
    pos_info = rm.calculate_position_size(
        equity=case["equity"],
        entry_price=case["entry_price"],
        stop_price=case["stop_price"],
    )

    if pos_info["size"] > 0:
        dollar_risk = pos_info["size"] * (pos_info["entry_price"] - pos_info["stop_price"])
        effective_pct = dollar_risk / case["equity"] * 100
    else:
        dollar_risk = 0.0
        effective_pct = 0.0

    results.append({
        "Label": case["label"],
        "Equity": case["equity"],
        "Entry": case["entry_price"],
        "Stop": case["stop_price"],
        "Size": pos_info["size"],
        "Dollar Risk": dollar_risk,
        "Risk Budget": pos_info.get("risk_amount", None),
        "Max Size": pos_info.get("max_size", None),
        "Effective % Risk": round(effective_pct, 3),
        "Reason": pos_info["reason"],
    })

# Convert to DataFrame for summary table
summary_df = pd.DataFrame(results)
print("\n=== Risk Manager Summary Table ===")
print(summary_df.to_string(index=False))
