import pandas as pd
import os # Import os to ensure the directory exists


def align_higher_timeframe(
    lower_df: pd.DataFrame,
    higher_df: pd.DataFrame,
    higher_tf_prefix: str = "D",
) -> pd.DataFrame:
    # ... (function body is the same as before) ...
    # Ensure indices are datetime and sorted
    lower_df = lower_df.copy().sort_index()
    higher_df = higher_df.copy().sort_index()

    # Shift higher timeframe by 1 period to avoid lookahead
    higher_df_shifted = higher_df.shift(1)

    # Rename columns to avoid collision
    higher_df_shifted = higher_df_shifted.add_prefix(f"{higher_tf_prefix}_")

    # Merge using backward fill (last known higher TF candle)
    aligned_df = pd.merge_asof(
        lower_df,
        higher_df_shifted,
        left_index=True,
        right_index=True,
        direction="backward",
    )

    return aligned_df


if __name__ == "__main__":
    # Load data
    df_4h = pd.read_csv("data/btc_usdt_4h.csv", index_col=0, parse_dates=True)
    df_1d = pd.read_csv("data/btc_usdt_1d.csv", index_col=0, parse_dates=True)

    aligned = align_higher_timeframe(df_4h, df_1d)

    print(aligned.head(10))
    print(aligned.columns)

    # --- ADDED CODE TO SAVE THE FILE ---
    output_path = "data/btc_usdt_aligned_4h_1d.csv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True) # Ensure the directory exists
    aligned.to_csv(output_path)
    print(f"\nSuccessfully saved the aligned data to {output_path}")
