from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict, List, Any


class Exchange(ABC):
    """
    Abstract base class for broker-agnostic exchange interface.
    Defines the contract for both paper and live brokers.
    """

    @abstractmethod
    def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> pd.DataFrame:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data.
        Returns a pandas DataFrame with standardized columns.
        """

    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """
        Return current account balances.
        Example: {"USDT": 1000.0, "BTC": 0.5}
        """

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        """
        Place an order.
        Returns a dict with order details.
        Example: {"order_id": "abc123", "status": "open", "filled": 0.0}
        """

    # --- Optional refinements for completeness ---

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order.
        Returns confirmation dict.
        """

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all currently open orders.
        Optionally filter by symbol.
        """

    @abstractmethod
    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Return current positions (for margin/futures accounts).
        Example: {"BTC/USDT": {"side": "long", "size": 0.5, "entry_price": 30000.0}}
        """
