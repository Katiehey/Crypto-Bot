import time
import ccxt
import pandas as pd

from src.execution.exchange import Exchange


class LiveBroker(Exchange):
    def __init__(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        sandbox: bool = True,
    ):
        exchange_class = getattr(ccxt, exchange_name)
        self.exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

        if sandbox and hasattr(self.exchange, "set_sandbox_mode"):
            self.exchange.set_sandbox_mode(True)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df.set_index("timestamp")

    def get_balance(self):
        balances = self.exchange.fetch_balance() 
        return {asset: balances["total"][asset] for asset in balances["total"]}

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float | None = None,
        order_type: str = "market",
        retries: int = 3,
    ):
        """
        Place an order with retry logic.
        Retries up to `retries` times with exponential backoff.
        """
        for attempt in range(retries):
            try:
                if order_type == "market":
                    return self.exchange.create_market_order(symbol, side, amount)
                else:
                    return self.exchange.create_limit_order(symbol, side, amount, price)
            except Exception as e:
                print(f"Order attempt {attempt+1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # backoff: 1s, 2s, 4s
                else:
                    raise
