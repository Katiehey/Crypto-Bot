import pandas as pd
import numpy as np

# ... (keep your sma, ema, rsi, bollinger_bands, and atr functions the same) ...

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()

def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()

def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    ma = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std()
    return ma, ma + num_std * std, ma - num_std * std

def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()

if __name__ == "__main__":
    # 1. Load the ALIGNED file (Cleaned 4h + Cleaned 1D shifted)
    # This file ensures no lookahead bias for the Daily indicators
    df = pd.read_csv("data/btc_usdt_aligned_4h_1d.csv", index_col=0, parse_dates=True)

    # --- 2. 4h INDICATORS (Execution/Timing) ---
    df["sma_20_4h"] = sma(df["close"], 20)
    df["sma_50_4h"] = sma(df["close"], 50)
    df["rsi_4h"] = rsi(df["close"], 14)
    df["atr_4h"] = atr(df, 14)
    
    # Bollinger Bands on 4h for entry/exit levels
    df["bb_mid_4h"], df["bb_upper_4h"], df["bb_lower_4h"] = bollinger_bands(df["close"], 20)

    # --- 3. DAILY INDICATORS (Trend Context) ---
    # We use the 'D_' columns created during the alignment process
    # D_close is the closing price of the PREVIOUS day (safe to use)
    
    # Fast vs Slow SMA on Daily to find the "Big Trend"
    df["sma_20_D"] = sma(df["D_close"], 20)
    df["sma_50_D"] = sma(df["D_close"], 50)
    
    # Daily RSI to see if the higher timeframe is overextended
    df["rsi_D"] = rsi(df["D_close"], 14)
    
    # Daily Bollinger Bands to see Daily volatility zones
    df["bb_mid_D"], df["bb_upper_D"], df["bb_lower_D"] = bollinger_bands(df["D_close"], 20)

    # --- 4. PREVIEW RESULTS ---
    print("Columns in DataFrame:", df.columns.tolist())
    print("\nLast 5 rows of calculated indicators:")
    # Only printing specific columns to make it readable in the terminal
    cols_to_show = ["close", "sma_20_4h", "sma_50_4h", "D_close", "sma_20_D", "sma_50_D", "rsi_4h"]
    print(df[cols_to_show].tail())

    # OPTIONAL: Save this as your final feature-ready dataset
    df.to_csv("data/btc_usdt_features.csv")
