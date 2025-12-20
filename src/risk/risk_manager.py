from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RiskConfig:
    # Defaults can be overridden by StrategyRouter per-strategy allocations
    risk_per_trade: float = 0.01     # fraction of equity risked per trade
    max_position_pct: float = 0.25   # max % of equity in one position
    min_trade_value: float = 10.0    # exchange minimum trade value
    precision: int = 6               # decimal precision for asset size


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
    ) -> Dict[str, Any]:
        """
        Calculate position size in units of asset, enforcing risk, caps, and minimums.
        Returns a dict with diagnostics for transparency.
        """

        # --- Safety check ---
        if stop_price >= entry_price or entry_price <= 0:
            return {"size": 0.0, "reason": "invalid stop/entry"}

        # --- Risk budget ---
        risk_amount = equity * self.config.risk_per_trade
        risk_per_unit = entry_price - stop_price
        raw_size = risk_amount / risk_per_unit

        # --- Max exposure cap ---
        max_position_value = equity * self.config.max_position_pct
        max_size = max_position_value / entry_price
        capped_size = min(raw_size, max_size)

        # --- Minimum trade value ---
        if capped_size * entry_price < self.config.min_trade_value:
            return {
                "size": 0.0,
                "reason": "below exchange minimum",
                "risk_amount": risk_amount,
                "max_size": max_size,
            }

        # --- Final rounded size ---
        final_size = round(capped_size, self.config.precision)

        return {
            "size": final_size,
            "risk_amount": risk_amount,
            "risk_per_unit": risk_per_unit,
            "max_size": max_size,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "reason": "ok",
        }
