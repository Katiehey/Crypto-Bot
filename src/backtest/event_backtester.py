import pandas as pd
import glob
import os


class EventBacktester:
    def __init__(
        self,
        initial_capital: float = 10_000.0,
        risk_per_trade: float = 0.003,  # fallback if intent doesn't provide per-strategy risk
        slippage: float = 0.0003,
        fee: float = 0.0004,
    ):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.slippage = slippage
        self.fee = fee

    def run(self, df: pd.DataFrame, intent: pd.DataFrame) -> pd.DataFrame:
        """
        df must include: open, high, low, close
        intent must include: intent, stop_price, source
        optionally: risk_per_trade (per-strategy allocation)
        """

        equity = self.initial_capital
        peak_equity = equity
        position = None
        entry_price = None
        stop_price = None
        position_size = 0
        source = None

        results = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_intent = intent.iloc[i - 1]

            # --- ENTRY ---
            if position is None and prev_intent["intent"] == "LONG":
                # Use per-strategy risk if available, else fallback
                risk_pt = (
                    prev_intent["risk_per_trade"]
                    if "risk_per_trade" in prev_intent and not pd.isna(prev_intent["risk_per_trade"])
                    else self.risk_per_trade
                )
                risk_amount = equity * risk_pt

                entry_price = row["open"] * (1 + self.slippage)
                stop_price = prev_intent["stop_price"]
                source = prev_intent.get("source", None)

                if stop_price is None or stop_price >= entry_price:
                    continue  # invalid risk

                position_size = risk_amount / (entry_price - stop_price)
                position = "LONG"

            # --- STOP LOSS ---
            if position == "LONG":
                if row["low"] <= stop_price:
                    exit_price = stop_price * (1 - self.slippage)
                    pnl = position_size * (exit_price - entry_price)
                    fee_cost = abs(position_size * exit_price) * self.fee
                    equity += pnl - fee_cost
                    peak_equity = max(peak_equity, equity)
                    drawdown = (peak_equity - equity) / peak_equity

                    results.append(
                        {
                            "exit_type": "STOP",
                            "pnl": pnl,
                            "equity": equity,
                            "drawdown": drawdown,
                            "source": source,
                        }
                    )

                    position = None
                    entry_price = None
                    stop_price = None
                    position_size = 0
                    source = None
                    continue

            # --- EXIT ON FLAT ---
            if position == "LONG" and prev_intent["intent"] == "FLAT":
                exit_price = row["open"] * (1 - self.slippage)
                pnl = position_size * (exit_price - entry_price)
                fee_cost = abs(position_size * exit_price) * self.fee
                equity += pnl - fee_cost
                peak_equity = max(peak_equity, equity)
                drawdown = (peak_equity - equity) / peak_equity

                results.append(
                    {
                        "exit_type": "SIGNAL",
                        "pnl": pnl,
                        "equity": equity,
                        "drawdown": drawdown,
                        "source": source,
                    }
                )

                position = None
                entry_price = None
                stop_price = None
                position_size = 0
                source = None

        return pd.DataFrame(results)

    def summary(self, trades: pd.DataFrame) -> pd.DataFrame:
        """
        Generate performance summary by strategy source + portfolio aggregate.
        """
        if trades.empty:
            return pd.DataFrame()

        # --- Per-strategy summary ---
        summary = trades.groupby("source").agg(
            trades_count=("pnl", "count"),
            win_rate=("pnl", lambda x: (x > 0).mean()),
            avg_pnl=("pnl", "mean"),
            total_pnl=("pnl", "sum"),
            max_drawdown=("drawdown", "max"),
            final_equity=("equity", "last"),
        )

        # --- Portfolio-level summary ---
        portfolio = pd.Series({
            "trades_count": len(trades),
            "win_rate": (trades["pnl"] > 0).mean(),
            "avg_pnl": trades["pnl"].mean(),
            "total_pnl": trades["pnl"].sum(),
            "max_drawdown": trades["drawdown"].max(),
            "final_equity": trades["equity"].iloc[-1],
        }, name="PORTFOLIO")

        # Append portfolio row
        summary = pd.concat([summary, portfolio.to_frame().T])

        return summary



if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

    # --- Automatically find the most recent final_intent file ---
    files = glob.glob("data/final_intent_*.csv")
    if not files:
        raise FileNotFoundError("No final_intent files found in data/ directory.")

    latest_file = max(files, key=os.path.getctime)
    print(f"Loading latest intent file: {latest_file}")

    intent = pd.read_csv(latest_file, index_col=0, parse_dates=True)

    bt = EventBacktester(initial_capital=500)
    results = bt.run(df, intent)

    print("\nBacktest results (last 5 trades):")
    print(results.tail())
    print("Total trades:", len(results))

    summary = bt.summary(results)
    print("\nPerformance Summary by Strategy:")
    print(summary)
