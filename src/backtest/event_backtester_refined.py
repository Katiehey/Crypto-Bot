from curses import window
import pandas as pd
import glob
import os
pd.set_option('future.no_silent_downcasting', True)

from src.risk.risk_manager import RiskManager, RiskConfig
from src.monitoring.logger import setup_logger 
from src.monitoring.alerts import AlertManager


class EventBacktester:
    def __init__(
        self,
        initial_capital: float = 100.0,
        risk_per_trade: float = 0.003,
        slippage: float = 0.0003,
        fee: float = 0.0004,
    ):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.slippage = slippage
        self.fee = fee

        # --- State tracking --- 
        self.equity = initial_capital 
        self.positions = {} 
        self.trade_log = []

        # --- Multi-stage partial exits ---
        # Format: (fraction_of_position, R_multiple)
        self.partial_exit_levels = [
            (0.10, 1.0),   # exit 25% at 1R 30
            (0.20, 2.0),  # exit 50% at 2R 30
            (0.30, 3.0),  # exit remaining 25% at 3R 20
            (0.50, None), # exit remaining 50% at final exit 20
        ]

        # Monitoring 
        self.logger = setup_logger("EventBacktester", "event_backtester.log") 
        self.alerts = AlertManager(self.logger)

    def run(self, df: pd.DataFrame, intent: pd.DataFrame, partial_exit_levels: list = None ) -> pd.DataFrame:
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
            
        # --- Diagnostics: print distribution before loop ---
        print("\nSentiment bucket counts:")
        print(df["sentiment_norm"].apply(sentiment_bucket).value_counts())

        print("\nIntent counts:")
        print(intent["intent"].value_counts())

        print("\nIntent vs Sentiment bucket:")
        print(intent["intent"].groupby(df["sentiment_norm"].apply(sentiment_bucket)).value_counts())

            
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_intent = intent.iloc[i - 1]
            sent_bucket = sentiment_bucket(row["sentiment_norm"])

            # --- Block EXTREME_GREED trades ---
            if position is None and prev_intent["intent"] == "LONG":
                if sent_bucket == "EXTREME_GREED":
                    results.append({
                        "timestamp": df.index[i],
                        "exit_type": "MARK",
                        "pnl": 0.0,
                        "pnl_pct": 0.0,
                        "equity": equity,
                        "drawdown": (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0,
                        "source": "BLOCKED",
                        "sentiment_bucket": sent_bucket,
                        "regime": row.get("regime", None),
                    })
                    continue
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
                # --- Guard against None stop_price ---
                if stop_price is None:
                    # fallback: ATR-based stop
                    if "atr_4h" in df.columns and not pd.isna(row["atr_4h"]):
                        stop_price = entry_price - 3 * row["atr_4h"]
                    elif "atr_D" in df.columns and not pd.isna(row["atr_D"]):
                        stop_price = entry_price - 1.5 * row["atr_D"]
                    else:
                        continue  # skip trade if no stop available

                sentiment = row.get("sentiment_norm")

                levels = partial_exit_levels or self.partial_exit_levels
                # --- Adaptive partial exit levels based on sentiment ---
                if sentiment is not None and 0.80 <= sentiment < 0.90:  # GREED only
                    levels = partial_exit_levels or [
                        (0.50, 1.0),
                        (0.30, 2.0),
                        (0.20, 3.0),
                        (0.0, None),   # 50% trailing
                    ]
                #40/30/15/15 (Aggressive early capture), 25/25/25/25 (Even distribution),20/30/20/30 (Trend‑biased capture),50/30/20/0* (No trailing, pure lock‑in),15/25/25/35 (Max trend capture with protection), 50,40,10,0 (Very aggressive early capture)



                for ratio, multiple in levels:
                    if multiple is None:
                        continue  # skip trailing exit in this loop
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
                            "pnl_pct": pnl_pct,
                            "equity": equity,
                            "drawdown": drawdown,
                            "source": source if source is not None else "UNKNOWN",
                            "sentiment_bucket": sent_bucket,
                            "regime": row.get("regime", None),  
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
                        # --- Guard against None stop_price ---
                        if stop_price is None:
                            if "atr_4h" in df.columns and not pd.isna(row["atr_4h"]):
                                stop_price = entry_price - 3 * row["atr_4h"]
                            else:
                                continue  # skip trade if no stop available
                        oneR_profit_stop = entry_price + (entry_price - stop_price)

                        regime = row["regime"] if "regime" in df.columns else None
                        sentiment = row["sentiment_norm"] if "sentiment_norm" in df.columns else None

                        if regime == "TREND":
                            # Sentiment-adaptive ATR multiplier
                            if sentiment is not None and sentiment > 0.90:
                                atr_mult = 4.5   # looser trailing in Extreme Greed
                            elif sentiment is not None and sentiment > 0.80:
                                atr_mult = 2.0   # tighter trailing in moderate Greed
                            else:
                                atr_mult = 3.0   # fallback
                            # ATR-based stops
                            atr_stop_4h = None
                            atr_stop_D = None

                            if "atr_4h" in df.columns and not pd.isna(row["atr_4h"]):
                                atr_stop_4h = row["close"] - atr_mult * row["atr_4h"]

                            if "atr_D" in df.columns and not pd.isna(row["atr_D"]):
                                # Daily ATR weighted lighter to avoid over-tightening
                                atr_stop_D = row["close"] - (atr_mult * 0.5) * row["atr_D"]

                            # Combine stops: take the max to give trades breathing room
                            stops = [s for s in [atr_stop_4h, atr_stop_D, oneR_profit_stop] if s is not None]
                            new_stop = max([stop_price] + stops)

                            if new_stop > stop_price:
                                stop_price = new_stop
                                print(df.index[i], "Stop updated via ATR TREND:", stop_price)

                        else:
                            # Non-TREND fallback
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
                    "source": source if source is not None else "UNKNOWN",
                    "sentiment_bucket": sent_bucket,
                    "regime": row.get("regime", None),  
                })

                # --- NEW ALERT --- 
                self.alerts.send("WARNING", f"Stop-loss triggered for {self.symbol}")

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
                    "source": source if source is not None else "UNKNOWN",
                    "sentiment_bucket": sent_bucket,
                    "regime": row.get("regime", None),  
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
                "source": source if source is not None else "UNKNOWN",
                "sentiment_bucket": sent_bucket,
                "regime": row.get("regime", None),  
            })
        df_results = pd.DataFrame(results)
        print("Results columns:", df_results.columns)
        return df_results

    
    def summary(self, trades: pd.DataFrame) -> pd.DataFrame:
        if trades.empty:
            return pd.DataFrame()

        # Ensure required columns exist
        for col in ["pnl", "drawdown", "source", "equity"]:
            if col not in trades.columns:
                if col == "source":
                    trades[col] = "UNKNOWN"
                elif col == "equity":
                    trades[col] = self.initial_capital  
                else:
                    trades[col] = 0.0

        if "source" in trades.columns:
            summary = trades.groupby("source").agg(
                trades_count=("pnl", "count"),
                win_rate=("pnl", lambda x: (x > 0).mean()),
                avg_pnl=("pnl", "mean"),
                total_pnl=("pnl", "sum"),
                max_drawdown=("drawdown", "max"),
                final_equity=("equity", "last"),
        )
        else:
            summary = pd.DataFrame()

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

# --- Metrics helper ---
def compute_metrics(df_results: pd.DataFrame):
    """
    Compute TRUE trade-based metrics.
    A trade = entry → all partial exits → final exit.
    """

    # --- Keep only executed exits (no MARK rows) ---
    exits = df_results[
        df_results["exit_type"].str.contains("PARTIAL|STOP|SIGNAL", regex=True)
    ].copy()

    if exits.empty:
        return {
            "expectancy": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "num_trades": 0,
            "max_dd": df_results["drawdown"].max() if "drawdown" in df_results else 0.0,
            "sharpe": 0.0,
        }

    # --- Identify trades ---
    # A STOP or SIGNAL closes a trade
    exits["trade_id"] = (exits["exit_type"].isin(["STOP", "SIGNAL"])).cumsum()

    # --- Aggregate to trade-level PnL ---
    trades = exits.groupby("trade_id").agg(
        trade_pnl=("pnl", "sum")
    )

    wins = trades[trades["trade_pnl"] > 0]
    losses = trades[trades["trade_pnl"] < 0]

    win_rate = len(wins) / len(trades)
    avg_win = wins["trade_pnl"].mean() if not wins.empty else 0.0
    avg_loss = losses["trade_pnl"].mean() if not losses.empty else 0.0  # negative

    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # --- Sharpe on trade-level returns ---
    sharpe = (
        trades["trade_pnl"].mean() / trades["trade_pnl"].std()
        if trades["trade_pnl"].std() != 0
        else 0.0
    )

    return {
        "expectancy": expectancy,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "num_trades": len(trades),
        "max_dd": df_results["drawdown"].max() if "drawdown" in df_results else 0.0,
        "sharpe": sharpe,
    }

    
# --- Strategy tester ---
EXIT_STRATEGIES = {
    "balanced_lock_in": [(0.20,1.0),(0.30,2.0),(0.20,3.0),(0.30,None)],
    "aggressive_early_capture": [(0.25,1.0),(0.25,2.0),(0.20,3.0),(0.30,None)],
    "max_trend_capture": [(0.15,1.0),(0.25,2.0),(0.20,3.0),(0.40,None)],
}

def test_exit_strategies(df, intent, backtester):
    results = []
    for name, levels in EXIT_STRATEGIES.items():
        # Apply exit levels to trades
        df_results = backtester.run(df, intent, partial_exit_levels=levels)
        metrics = compute_metrics(df_results)
        results.append({
            "strategy": name,
            "expectancy": metrics["expectancy"],
            "win_rate": metrics["win_rate"],
            "avg_win": metrics["avg_win"],
            "avg_loss": metrics["avg_loss"],
            "max_dd": metrics["max_dd"],
            "sharpe": metrics["sharpe"],
        })
    return pd.DataFrame(results) 

    
    



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

    logger = setup_logger("Backtest", "backtest.log") 
    alerts = AlertManager(logger)

    bt = EventBacktester(initial_capital=500, logger=logger, alerts=alerts)
    results = bt.run(df, intent)

    print("\nBacktest results (last 5 trades):")
    print(results.tail())
    print("Total trades:", len(results))

    #summary = bt.summary(results)
    #print("\nPerformance Summary by Strategy:")
    #print(summary)

    # --- Performance summary ---
    summary = compute_metrics(results)
    print("\nPerformance Summary:")
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

    print(results.groupby("regime")["pnl_pct"].mean())

    

    

    
