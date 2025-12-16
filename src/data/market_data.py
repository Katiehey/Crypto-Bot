import ccxt
import pandas as pd
from datetime import datetime, timezone
import time
import os
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

        # Print a message to indicate which timeframe is being downloaded
        print(f"Starting download for {self.symbol} with timeframe {self.timeframe}...")

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
            # Use the timestamp of the last candle to fetch the next batch
            since = candles[-1][0] + 1

            # Respect rate limits
            # time.sleep(self.exchange.rateLimit / 1000) # Optional: uncomment if hitting rate limits often

            # Stop if the last fetch was not a full limit, indicating we reached the end of available data
            if len(candles) < self.limit:
                break
        
        print(f"Finished downloading {len(all_candles)} candles for {self.timeframe}.")

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
        # Ensure the directory exists before saving
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path)
        print(f"Saved {len(df)} rows to {path}")


if __name__ == "__main__":
    # Common parameters
    EXCHANGE = "binance"
    SYMBOL = "BTC/USDT"
    SINCE_DATE = "2019-01-01"
    
    # --- Download 4h data ---
    downloader_4h = MarketDataDownloader(
        exchange_name=EXCHANGE,
        symbol=SYMBOL,
        timeframe="4h",
        since=SINCE_DATE,
    )
    df_4h = downloader_4h.fetch_ohlcv()
    downloader_4h.save_to_csv(df_4h, "data/btc_usdt_4h.csv")

    print("-" * 30) # Separator for clarity

    # --- Download 1d data ---
    downloader_1d = MarketDataDownloader(
        exchange_name=EXCHANGE,
        symbol=SYMBOL,
        timeframe="1d",
        since=SINCE_DATE,
    )
    df_1d = downloader_1d.fetch_ohlcv()
    downloader_1d.save_to_csv(df_1d, "data/btc_usdt_1d.csv")
