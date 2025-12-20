import pandas as pd
import glob
import os
pd.set_option('future.no_silent_downcasting', True)

from src.risk.risk_manager import RiskManager, RiskConfig


class EventBacktester:
    def __init__(
        self,
        initial_capital: float = 500.0,
        risk_per_trade: float = 0.003,
        slippage: float = 0.0003,
        fee: float = 0.0004,
    ):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.slippage = slippage
        self.fee = fee

        # --- Multi-stage partial exits ---
        # Format: (fraction_of_position, R_multiple)
        self.partial_exit_levels = [
            (0.5, 1.0),   # exit 50% at 1R
            (0.25, 2.0),  # exit 25% at 2R
        ]

    def run(self, df: pd.DataFrame, intent: pd.DataFrame) -> pd.DataFrame:
        equity = self.initial_capital
        peak_equity = equity

        position = None
        entry_price = None
        stop_price = None
        position_size = 0.0
        source = None
        partial_exits_taken = set()
        results = []

        def sentiment_bucket(val):
            if val <= 0.20:
                return "EXTREME_FEAR"
            elif val <= 0.35:
                return "FEAR/NEUTRAL"
            elif val <= 0.65:
                return "GREED"
            else:
                return "EXTREME_GREED"
            
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_intent = intent.iloc[i - 1]
            sent_bucket = sentiment_bucket(row["sentiment_norm"])

            # --- ENTRY (LONG) ---
            if position is None and prev_intent["intent"] == "LONG":
                risk_pt = (
                    prev_intent["risk_per_trade"]
                    if ("risk_per_trade" in prev_intent and not pd.isna(prev_intent["risk_per_trade"]))
                    else self.risk_per_trade
                )

                entry_price = row["open"] * (1 + self.slippage)
                stop_price = prev_intent["stop_price"]
                source = prev_intent.get("source", None)

                if stop_price is None or stop_price >= entry_price:
                    continue

                risk_cfg = RiskConfig(
                    risk_per_trade=risk_pt,
                    max_position_pct=0.25,
                    min_trade_value=15.0,
                )

                risk_mgr = RiskManager(risk_cfg)
                pos_info = risk_mgr.calculate_position_size(
                    equity=equity,
                    entry_price=entry_price,
                    stop_price=stop_price,
                )

                if pos_info["size"] <= 0:
                    continue

                position_size = float(pos_info["size"])
                position = "LONG"
                partial_exits_taken = set()

            # --- PARTIAL EXITS ---
            if position == "LONG" and position_size > 0:
                for ratio, multiple in self.partial_exit_levels:
                    if multiple in partial_exits_taken:
                        continue
                    r_target = entry_price + (entry_price - stop_price) * multiple
                    if row["high"] >= r_target:
                        exit_price = r_target * (1 - self.slippage)
                        partial_size = position_size * ratio
                        pnl = partial_size * (exit_price - entry_price)
                        pnl_pct = pnl / equity if equity != 0 else 0.0
                        fee_cost = abs(partial_size * exit_price) * self.fee
                        equity += pnl - fee_cost
                        peak_equity = max(peak_equity, equity)
                        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                        results.append({
                            "timestamp": df.index[i],
                            "exit_type": f"PARTIAL_{multiple}R",
                            "pnl": pnl,
                            "equity": equity,
                            "drawdown": drawdown,
                            "source": source,
                            "sentiment_bucket": sent_bucket,
                        })
                        position_size -= partial_size
                        partial_exits_taken.add(multiple)

                # --- Progressive trailing stops ---
                if position == "LONG":
                    # After 1R partial: trail to breakeven
                    if 1.0 in partial_exits_taken:
                        breakeven_stop = entry_price * (1 - self.slippage - self.fee)
                        stop_price = max(stop_price, breakeven_stop)

                     # After 2R partial: trail to +1R profit OR ATR-based dynamic stop
                    if 2.0 in partial_exits_taken:
                        # Fixed +1R profit stop
                        oneR_profit_stop = entry_price + (entry_price - stop_price)

                        # Regime-specific ATR trailing
                        regime = row["regime"] if "regime" in df.columns else None
                        if regime == "TREND" and "atr_4h" in df.columns and not pd.isna(row["atr_4h"]):
                            atr_stop = row["close"] - 2.5 * row["atr_4h"]   # looser trailing in trends
                            stop_price = max(stop_price, oneR_profit_stop, atr_stop)
                            print(df.index[i], "Stop updated via ATR TREND:", stop_price)
                        elif regime == "RANGE" and "atr_D" in df.columns and not pd.isna(row["atr_D"]):
                            atr_stop = row["close"] - 1.0 * row["atr_D"]    # tighter trailing in ranges
                            stop_price = max(stop_price, oneR_profit_stop, atr_stop)
                            print(df.index[i], "Stop updated via ATR RANGE:", stop_price)
                        else:
                            stop_price = max(stop_price, oneR_profit_stop)
                        print(df.index[i], "Stop updated via ATR:", stop_price)

            # --- STOP LOSS ---
            if position == "LONG" and position_size > 0 and row["low"] <= stop_price:
                exit_price = stop_price * (1 - self.slippage)
                pnl = position_size * (exit_price - entry_price)
                pnl_pct = pnl / equity if equity != 0 else 0.0
                fee_cost = abs(position_size * exit_price) * self.fee
                equity += pnl - fee_cost
                peak_equity = max(peak_equity, equity)
                drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                results.append({
                    "timestamp": df.index[i],
                    "exit_type": "STOP",
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "equity": equity,
                    "drawdown": drawdown,
                    "source": source,
                    "sentiment_bucket": sent_bucket,
                })
                position = None
                entry_price = None
                stop_price = None
                position_size = 0.0
                source = None
                partial_exits_taken = set()
                continue

            # --- EXIT ON FLAT ---
            if position == "LONG" and position_size > 0 and prev_intent["intent"] == "FLAT":
                exit_price = row["open"] * (1 - self.slippage)
                pnl = position_size * (exit_price - entry_price)
                fee_cost = abs(position_size * exit_price) * self.fee
                equity += pnl - fee_cost
                peak_equity = max(peak_equity, equity)
                drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                pnl_pct = pnl / equity if equity != 0 else 0.0
                results.append({
                    "timestamp": df.index[i],
                    "exit_type": "SIGNAL",
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "equity": equity,
                    "drawdown": drawdown,
                    "source": source,
                    "sentiment_bucket": sent_bucket,
                })
                position = None
                entry_price = None
                stop_price = None
                position_size = 0.0
                source = None
                partial_exits_taken = set()

            # --- MARK-TO-MARKET (always record equity each bar) ---
            results.append({
                "timestamp": df.index[i],
                "exit_type": "MARK",
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "equity": equity,
                "drawdown": (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0,
                "source": source,
                "sentiment_bucket": sent_bucket,
            })
        return pd.DataFrame(results)


    def summary(self, trades: pd.DataFrame) -> pd.DataFrame:
        if trades.empty:
            return pd.DataFrame()

        summary = trades.groupby("source").agg(
            trades_count=("pnl", "count"),
            win_rate=("pnl", lambda x: (x > 0).mean()),
            avg_pnl=("pnl", "mean"),
            total_pnl=("pnl", "sum"),
            max_drawdown=("drawdown", "max"),
            final_equity=("equity", "last"),
        )

        portfolio = pd.Series({
            "trades_count": len(trades),
            "win_rate": (trades["pnl"] > 0).mean(),
            "avg_pnl": trades["pnl"].mean(),
            "total_pnl": trades["pnl"].sum(),
            "max_drawdown": trades["drawdown"].max(),
            "final_equity": trades["equity"].iloc[-1],
        }, name="PORTFOLIO")

        summary = pd.concat([summary, portfolio.to_frame().T])
        return summary


if __name__ == "__main__":
    df = pd.read_csv(
        "data/btc_usdt_features.csv",
        index_col=0,
        parse_dates=True,
    )

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

    # --- Sentiment diagnostics ---
    print("\nSentiment diagnostics:")

    print("\nTrades per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["exit_type"].count())

    print("\nAverage PnL per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].mean())

    print("\nTotal PnL per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].sum())

    print("\nWin rate per sentiment bucket:")
    print(results.groupby("sentiment_bucket")["pnl"].apply(lambda x: (x > 0).mean()))
