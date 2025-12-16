import requests
import pandas as pd


class FearGreedIndex:
    def __init__(self):
        self.url = "https://api.alternative.me/fng/"

    def fetch(self, limit: int = 0) -> pd.DataFrame:
        """
        Fetch Fear & Greed Index data.

        limit=0 -> full history
        """
        params = {"limit": limit, "format": "json"}
        response = requests.get(self.url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()["data"]

        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df.set_index("timestamp", inplace=True)

        df["value"] = df["value"].astype(float)

        return df.sort_index()

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize Fear & Greed Index to [0, 1]
        """
        df = df.copy()
        df["sentiment_norm"] = df["value"] / 100.0
        return df

    def save_to_csv(self, df: pd.DataFrame, path: str):
        df.to_csv(path)
        print(f"Saved sentiment data to {path}")

if __name__ == "__main__":
    fng = FearGreedIndex()
    df = fng.fetch(limit=0)
    df = fng.normalize(df)

    print(df.tail())
    fng.save_to_csv(df, "data/fear_greed_index.csv")
