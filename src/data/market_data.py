import ccxt
import pandas as pd
from datetime import datetime, timezone
import time
from typing import Optional


class MarketDataDownloader:
    def __init__(
        self,
        exchange_name: str = "binance",
        symbol: str = "BTC/USDT",
        timeframe: str = "4h",
        since: Optional[str] = None,
        limit: int = 1000,
    ):
        self.exchange_name = exchange_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.limit = limit

        self.exchange = getattr(ccxt, exchange_name)({
            "enableRateLimit": True,
        })

        self.since = (
            int(pd.Timestamp(since, tz="UTC").timestamp() * 1000)
            if since
            else None
        )

    def fetch_ohlcv(self) -> pd.DataFrame:
        all_candles = []
        since = self.since

        while True:
            candles = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=self.timeframe,
                since=since,
                limit=self.limit,
            )

            if not candles:
                break

            all_candles.extend(candles)
            since = candles[-1][0] + 1

            # Respect rate limits
            time.sleep(self.exchange.rateLimit / 1000)

            if len(candles) < self.limit:
                break

        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        df = df[~df.index.duplicated(keep="first")]
        df.sort_index(inplace=True)

        return df

    def save_to_csv(self, df: pd.DataFrame, path: str):
        df.to_csv(path)
        print(f"Saved {len(df)} rows to {path}")


if __name__ == "__main__":
    downloader = MarketDataDownloader(
        exchange_name="binance",
        symbol="BTC/USDT",
        timeframe="4h",
        since="2019-01-01",
    )

    df = downloader.fetch_ohlcv()
    downloader.save_to_csv(df, "data/btc_usdt_4h.csv")
