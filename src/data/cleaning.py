import pandas as pd
import os # Import os for directory creation/checking


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans OHLCV data:
    - Ensures datetime index
    - Sorts chronologically
    - Removes duplicates
    - Casts numeric columns
    """
    df = df.copy()

    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        # If the index isn't a datetime index yet, try to convert it
        df.index = pd.to_datetime(df.index, utc=True)

    # Sort by time
    df.sort_index(inplace=True)

    # Remove duplicate timestamps
    df = df[~df.index.duplicated(keep="first")]

    # Enforce numeric types
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            # Use errors='coerce' to turn anything that can't be a number into NaN
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def detect_missing_candles(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Detect missing candles without filling them.
    Returns a dataframe of missing timestamps.
    """
    freq_map = {
        "4h": "4H",
        "1d": "1D",
    }
    if timeframe not in freq_map:
        raise ValueError("Unsupported timeframe")

    expected_index = pd.date_range(
        start=df.index.min(),
        end=df.index.max(),
        freq=freq_map[timeframe],
        tz=df.index.tz,
    )
    missing = expected_index.difference(df.index)
    return pd.DataFrame(index=missing)


def forward_fill_volume_zero(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill OHLC values ONLY if volume is zero.
    This handles rare exchange glitches.
    """
    df = df.copy()
    zero_volume = df["volume"] == 0
    ohlc_cols = ["open", "high", "low", "close"]
    # Only apply ffill where volume is exactly zero
    df.loc[zero_volume, ohlc_cols] = df.loc[zero_volume, ohlc_cols].ffill()
    return df

# --- NEW FUNCTION TO HANDLE THE FULL PROCESS ---

def process_and_save_data(input_path: str, output_path: str, timeframe: str):
    print(f"--- Starting processing for {input_path} (Timeframe: {timeframe}) ---")

    # Load data
    df = pd.read_csv(
        input_path,
        index_col=0,
        parse_dates=True,
    )

    # Clean the data
    df_clean = clean_ohlcv(df)
    
    # Detect missing candles (for informational purposes)
    missing = detect_missing_candles(df_clean, timeframe=timeframe)
    print(f"  Missing candles detected: {len(missing)}")

    # Handle zero volume glitches
    df_clean = forward_fill_volume_zero(df_clean)

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save the clean data back to a file
    df_clean.to_csv(output_path)
    print(f"  Successfully cleaned and saved to {output_path}")
    print(f"  Total rows saved: {len(df_clean)}\n")


if __name__ == "__main__":
    # Define file paths
    path_4h_in = "data/btc_usdt_4h.csv"
    path_4h_out = "data/btc_usdt_4h.csv"
    path_1d_in = "data/btc_usdt_1d.csv"
    path_1d_out = "data/btc_usdt_1d.csv"

    # Process both timeframes using the new function
    process_and_save_data(path_4h_in, path_4h_out, timeframe="4h")
    process_and_save_data(path_1d_in, path_1d_out, timeframe="1d")
