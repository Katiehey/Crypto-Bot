import pandas as pd
import numpy as np
from enum import Enum
from src.regime.regime_detector import MarketRegime


class BollingerSignal(Enum):
    LONG = "LONG"
    FLAT = "FLAT"


class BollingerStrategy:
    def __init__(self, atr_stop_mult: float = 1.5):
        self.atr_stop_mult = atr_stop_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        required = ["close", "regime", "enabled_strategies", "sentiment_norm",
                    "bb_mid_D", "bb_upper_D", "bb_lower_D", "atr_D"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        df["signal"] = BollingerSignal.FLAT.value
        df["stop_price"] = np.nan

        # --- Entry condition ---
        long_condition = (
            (df["regime"] == MarketRegime.RANGE.value)
            & (df["close"] > df["bb_upper_D"])
            & (df["enabled_strategies"].apply(lambda s: "BOLLINGER" in s if isinstance(s, list) else False))
            & (df["sentiment_norm"] > 0.35)   # only allow Fear (0.35–0.5), Greed, Extreme Greed
        )

        df.loc[long_condition, "signal"] = BollingerSignal.LONG.value
        df.loc[long_condition, "stop_price"] = df["close"] - df["atr_D"] * self.atr_stop_mult

        # --- Exit condition ---
        exit_condition = (
            (df["close"] < df["bb_mid_D"])      # price falls back below mid-band
            | (df["sentiment_norm"] <= 0.35)    # force exit in Neutral or Extreme Fear
            | (df["enabled_strategies"].apply(lambda s: "BOLLINGER" not in s if isinstance(s, list) else True))
        )
        df.loc[exit_condition, "signal"] = BollingerSignal.FLAT.value
        df.loc[exit_condition, "stop_price"] = np.nan

        # --- Persistence ---
        df["signal"] = (
            df["signal"].replace(BollingerSignal.FLAT.value, np.nan).ffill().fillna(BollingerSignal.FLAT.value)
        )
        df["stop_price"] = df["stop_price"].ffill()
        df.loc[df["signal"] == BollingerSignal.FLAT.value, "stop_price"] = np.nan

        # --- Final sentiment override ---
        df.loc[df["sentiment_norm"] <= 0.35, "signal"] = BollingerSignal.FLAT.value
        df.loc[df["sentiment_norm"] <= 0.35, "stop_price"] = np.nan

        return df[["signal", "stop_price", "bb_upper_D", "bb_lower_D", "bb_mid_D", "atr_D", "sentiment_norm"]]



if __name__ == "__main__":
    import pandas as pd
    from src.regime.regime_detector import RegimeDetector

    # 1) Load full features (includes OHLC + precomputed indicators)
    features_df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    # 2) Run regime detection separately
    detector = RegimeDetector()
    regimes = detector.detect(features_df.copy())

    # 3) Merge regime outputs back onto features
    df = features_df.join(regimes[["enabled_strategies"]], how="left")


    # --- Debug prints here ---
    print("features_df cols:", list(features_df.columns)[:10], "... total:", len(features_df.columns))
    print("regimes cols:", list(regimes.columns))
    print("merged df cols:", list(df.columns))
    print("merged df rows:", len(df))
    print("sample row enabled_strategies:", df['enabled_strategies'].iloc[0])
    print("has close?", "close" in df.columns, "has bb_mid_D?", "bb_mid_D" in df.columns)

    # 4) Generate signals
    strat = BollingerStrategy()
    signals = strat.generate_signals(df)

    # 5) Diagnostics
    print(signals.tail(20))
    print("\nSignal distribution:")
    print(signals["signal"].value_counts())

    print("\nSignals by sentiment bucket (refined):")
    sentiment_bins = pd.cut(
    signals["sentiment_norm"],
    bins=[0, 0.25, 0.35, 0.5, 0.75, 1.0],
    labels=["Extreme Fear", "Neutral", "Fear", "Greed", "Extreme Greed"]
    )
    diagnostic = signals.groupby(sentiment_bins)["signal"].value_counts()
    print(diagnostic)

