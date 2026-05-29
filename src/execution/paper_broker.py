import pandas as pd
from datetime import datetime
from src.execution.exchange import Exchange
from typing import Optional, Dict, List, Any
from src.monitoring.alerts import AlertManager 
from src.monitoring.logger import setup_logger
from src.state.state_store import StateStore


class PaperBroker(Exchange):
    """Simulated exchange broker for paper trading.

    Reads historical OHLCV data from a CSV file and fills orders at the
    last closing price. State (equity, positions, trade log) is persisted to
    a JSON file after every trade so the bot can resume cleanly on restart.
    """

    def __init__(
        self,
        starting_balance: float = 100.0,
        data_path: str = "data/btc_usdt_features.csv",
        state_path: str = "state/paper_state.json",
    ):
        self.balance = starting_balance
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_log: List[Dict[str, Any]] = []
        self.data_path = data_path 
        # --- State persistence ---
        self.state_store = StateStore(state_path, initial_equity=starting_balance)
        state = self.state_store.load()
        self.balance = state.get("equity", starting_balance) 
        self.positions: Dict[str, Dict[str, Any]] = state.get("positions", {})
        self.trade_log: List[Dict[str, Any]] = state.get("trade_log", [])
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        self.next_order_id = len(self.trade_log) + 1

        # preload OHLCV data
        self.ohlcv_data = pd.read_csv(self.data_path, parse_dates=["timestamp"])
        self.ohlcv_data.set_index("timestamp", inplace=True)

        # Monitoring 
        self.logger = setup_logger("PaperBroker", "paper_broker.log") 
        self.alerts = AlertManager(self.logger)

    def _persist_state(self): 
        """Save current broker state to JSON file.""" 
        state = { 
            "equity": self.balance, 
            "positions": self.positions, 
            "trade_log": self.trade_log, 
            } 
        self.state_store.save(state)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Return the most recent `limit` rows of preloaded OHLCV data."""
        #raise ConnectionError("Simulated exchange failure")
        return self.ohlcv_data.tail(limit).copy()

    def get_balance(self) -> Dict[str, float]:
        """Return current simulated USDT balance."""
        return {"USDT": self.balance}

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        reason: str = None,
    ) -> Dict[str, Any]:
        """Simulate placing a buy or sell order.

        Market orders fill immediately at the last close price with a 0.05% fee.
        Limit orders are queued in open_orders until cancelled or matched.

        Args:
            symbol: Trading pair, e.g. "BTC/USDT".
            side: "buy" or "sell".
            amount: Asset quantity to trade.
            price: Limit price; ignored for market orders.
            order_type: "market" (default) or "limit".
            reason: Optional tag logged with the trade ("STOP", "SIGNAL", etc.).

        Returns:
            Order dict with order_id, symbol, side, price, amount, and status.
        """
        #raise ValueError("Order rejected: insufficient funds")
        order_id = str(self.next_order_id)
        self.next_order_id += 1

        # Determine fill price
        if order_type == "market":
            fill_price = self.ohlcv_data["close"].iloc[-1]
        else:
            fill_price = price

        cost = fill_price * amount
        fee = cost * 0.0005

        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": fill_price,
            "status": "open" if order_type == "limit" else "filled",
            "time": datetime.utcnow(),
        }

        if order_type == "market":
            # Fill immediately
            if side == "buy":
                self.balance -= (cost + fee)
                pos = self.positions.get(symbol, {"amount": 0, "entry_price": 0})
                total_amount = pos["amount"] + amount
                avg_entry = (
                    (pos["entry_price"] * pos["amount"] + fill_price * amount) / total_amount
                )
                self.positions[symbol] = {"amount": total_amount, "entry_price": avg_entry}

            elif side == "sell":
                pos = self.positions.get(symbol)
                if not pos or pos["amount"] < amount:
                    raise ValueError("Not enough position to sell")
                self.balance += cost - fee
                pos["amount"] -= amount
                if pos["amount"] == 0:
                    self.positions.pop(symbol)
                    # --- Trigger alert if stop-loss close --- 
                    if reason == "STOP": 
                        self.alerts.send("WARNING", f"Stop-loss triggered for {symbol}")
                else:
                    self.positions[symbol] = pos

            order["status"] = "filled"

        else:
            # Limit order stays open until cancelled or matched
            self.open_orders[order_id] = order

        self.trade_log.append({
            "time": order["time"],
            "symbol": symbol,
            "side": side,
            "price": fill_price,
            "amount": amount,
            "balance": self.balance,
            "status": order["status"],
            "reason": reason,
        })

        # --- Persist state after every trade --- 
        self._persist_state()

        return order

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open limit order. Returns status "not_found" if the ID is unknown."""
        order = self.open_orders.pop(order_id, None)
        if not order:
            return {"status": "not_found", "order_id": order_id}
        order["status"] = "cancelled"
        self._persist_state()
        return order

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all open limit orders, optionally filtered by symbol."""
        orders = list(self.open_orders.values())
        if symbol:
            orders = [o for o in orders if o["symbol"] == symbol]
        return orders

    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Return open positions, optionally filtered to a single symbol."""
        if symbol:
            return {symbol: self.positions.get(symbol)}
        return self.positions
