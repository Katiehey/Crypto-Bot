import os
import time
import pandas as pd
import numpy as np
import datetime
import json
from src.monitoring.logger import setup_logger
from src.monitoring.alerts import AlertManager

pd.set_option('future.no_silent_downcasting', True)

from src.execution.paper_broker import PaperBroker
from src.regime.regime_detector import RegimeDetector
from src.strategies.trend_following_refined import TrendFollowingStrategy
from src.strategies.mean_reversion_refined import MeanReversionStrategy
from src.engine.strategy_router_refined import StrategyRouter, TradeIntent
from src.risk.risk_manager import RiskManager, RiskConfig
from src.config.config import ConfigError, ConfigLoader
from src.execution.paper_broker import PaperBroker 
from src.execution.live_broker import LiveBroker
from src.state.state_store import StateStore
from src.monitoring.heartbeat import Heartbeat
from src.infra.backup_manager import create_backup
from src.backtest.event_backtester_refined import EventBacktester



class TradingBot:
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1d",
        sleep_seconds: int = 60 * 60 * 4,  # 4H
        force_extreme_greed: bool = False,
        cooldown_bars: int = 1,  # number of bars to cooldown after stop-loss
    ):
        self.heartbeat = Heartbeat()
        self.symbol = symbol
        self.timeframe = timeframe
        self.sleep_seconds = sleep_seconds
        self.force_extreme_greed = force_extreme_greed
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.cooldown_bars = cooldown_bars # configurable, e.g. 1 for daily, 3 for 4h
        # Load config
        self.config = ConfigLoader().load()
        self.mode = self.config["mode"]
        self.summary_hour = int(os.getenv("SUMMARY_HOUR", "18")) 
        self.summary_minute = int(os.getenv("SUMMARY_MINUTE", "0"))
        self.last_backup = 0 
        self.backup_interval = 60 * 60 # hourly

        # --- Centralized initial balance --- 
        initial_balance = ( 
            self.config.get("account", {}).get("initial_balance") 
            or self.config.get("risk", {}).get("starting_balance") 
            or 100.0 
        )

        if self.mode == "paper": 
            self.broker = PaperBroker( 
                starting_balance=initial_balance,
                data_path=self.config["exchange"].get("data_path", "data/btc_usdt_features.csv"), 
            ) 
            self.state = StateStore( 
                path="state/paper_state.json", 
                initial_equity=initial_balance, 
            ) 
            self.backtester = EventBacktester( 
                initial_capital=initial_balance, 
                risk_per_trade=self.config["risk"].get("risk_per_trade", 0.01), 
            )
            
        elif self.mode in {"sandbox", "live"}: 
            self.broker = LiveBroker( 
                exchange_name=self.config["exchange"]["name"], 
                api_key=self.config.get("api_key"), 
                api_secret=self.config.get("api_secret"), 
                sandbox=self.config["exchange"].get("sandbox", False), 
                ) 
        else: 
            raise ConfigError(f"Unsupported mode: {self.mode}")

        # Core components
        self.regime_detector = RegimeDetector()
        self.trend_strategy = TrendFollowingStrategy()
        self.mr_strategy = MeanReversionStrategy()

        self.position = None
        self.starting_equity = self.broker.get_balance()["USDT"]

        # Monitoring
        self.logger = setup_logger("TradingBot", "trading_bot.log")
        self.alerts = AlertManager(self.logger)

        self.logger.info("Bot initialized | symbol=%s timeframe=%s", self.symbol, self.timeframe)

        self.strategy_router = StrategyRouter()

        self.heartbeat.beat( 
            status="STARTING", 
            details={ 
                "mode": self.mode, 
                "symbol": self.symbol, 
                "timeframe": self.timeframe, 
            }, 
        )
        self.alerts.send("INFO", f"🚀 {self.symbol} bot started in {self.mode} mode", include_info=True)

        # Track last summary date
        self.last_summary_date = None

    def check_daily_loss(self, results_df, threshold_pct=0.05):
        today = datetime.datetime.utcnow().date()

        # Ensure timestamp column exists 
        if "timestamp" not in results_df.columns: 
            results_df = results_df.copy() 
            results_df["timestamp"] = results_df.index

        pnl_today = results_df[results_df["timestamp"].dt.date == today]["pnl"].sum()
        if pnl_today < -threshold_pct * self.starting_equity:
            self.alerts.send("CRITICAL", f"Daily loss exceeded {threshold_pct*100:.1f}% | pnl={pnl_today:.2f}")
            self.heartbeat.beat("ERROR", {"error": "Daily loss threshold exceeded"})
            raise SystemExit()
        
    def update_consecutive_losses(self, trade_pnl):
        if trade_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self.consecutive_losses >= 3:
            self.alerts.send("CRITICAL", "3 consecutive losses. Bot paused for safety.")
            time.sleep(86400)  # pause for 1 day

    def check_position_consistency(self):
        broker_pos = self.broker.get_positions(self.symbol)
        if self.position and not broker_pos.get(self.symbol):
            self.alerts.send("CRITICAL", "Unexpected position mismatch. Bot halted.")
            raise SystemExit()

    def check_heartbeat_freshness(self, max_age_seconds: int = 900): 
        """ Verify that heartbeat.json has been updated recently. 
        max_age_seconds: allowed age in seconds (default 15 minutes). 
        """ 
        hb_path = os.path.join("state", "heartbeat.json") 
        if not os.path.exists(hb_path): 
            self.logger.warning("Heartbeat file missing") 
            return False 
        try: 
            with open(hb_path, "r") as f: 
                hb = json.load(f) 
            ts = hb.get("timestamp") 
            if not ts: 
                self.logger.warning("Heartbeat missing timestamp") 
                return False 
            # Parse ISO timestamp 
            ts_dt = datetime.datetime.fromisoformat(ts.replace("Z", "")) 
            age = (datetime.datetime.utcnow() - ts_dt).total_seconds() 
            if age > max_age_seconds: 
                self.logger.error(f"Heartbeat stale: {age:.0f}s old") 
                self.alerts.send("CRITICAL", f"Heartbeat stale: {age:.0f}s old") 
                return False 
            return True 
        except Exception as e: 
            self.logger.exception("Failed to check heartbeat freshness") 
            return False

    def maybe_backup(self):
        now = time.time()
        if now - self.last_backup > self.backup_interval:
            create_backup()
            self.last_backup = now
            self.logger.info("Backup created successfully")

    def run_once(self):
        """Run a single cycle of the trading bot logic."""
        self.logger.info("Fetching market data...")
        self.heartbeat.beat(
            status="RUNNING",
            details={
                "mode": self.mode,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
            },
        )

        try:
            df = self.broker.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            regime_df = self.regime_detector.detect(df)
            df = df.drop(columns=["trend_strength", "regime", "sentiment_norm"], errors="ignore") 
            df = df.join(regime_df)


            # --- Sentiment --- 
            if self.force_extreme_greed: 
                df["sentiment_norm"] = 0.8 
                self.logger.warning("Sentiment forced to Extreme Greed for testing") 
            else: 
                df["sentiment_norm"] = 0.5

            # --- Strategy Signals --- 
            trend_signals = self.trend_strategy.generate_signals(df) 
            mr_signals = self.mr_strategy.generate_signals(df) 
            boll_signals = pd.DataFrame({ "signal": [None] * len(df), "stop_price": [None] * len(df), }, index=df.index) 
            
            # --- Route Intent --- 
            intent_df = self.strategy_router.route(df, trend_signals, mr_signals, boll_signals) 
            latest = df.iloc[-1] 
            latest_intent = intent_df.iloc[-1]

            # Update heartbeat 
            self.heartbeat.beat( 
                status="running", 
                details={"symbol": self.symbol, "regime": latest["regime"], "intent": latest_intent["intent"],
                }, 
            )

            self.logger.info( 
                f"Regime={latest['regime']} | Intent={latest_intent['intent']} | " 
                f"TrendSignal={trend_signals.iloc[-1]['signal']} | " 
                f"Volume={latest['volume']} vs avg={df['volume'].rolling(20).mean().iloc[-1]}" 
            )

        except Exception as e:
            self.logger.exception("Bot crashed")
            self.heartbeat.beat(status="error", details={"error": str(e)})
            self.alerts.send("CRITICAL", f"Exchange connection failure: {e}")
            raise

        balance = self.broker.get_balance()["USDT"]

        # Drawdown guard
        if balance < self.starting_equity * 0.8:
            self.alerts.send("CRITICAL", "Equity drawdown exceeded 20%. Bot halted.")
            self.heartbeat.beat("ERROR", {"error": "Equity drawdown exceeded 20%"})
            raise SystemExit()

        # --- Cooldown guard ---
        if self.cooldown_until and latest.name <= self.cooldown_until:
            self.logger.info("Cooldown active, skipping trades")
            self.heartbeat.beat("IDLE")
            return intent_df

        # --- Entry logic ---
        if self.position is None and latest_intent["intent"] == TradeIntent.LONG.value:
            entry_price = latest["close"]
            stop_price = latest_intent["stop_price"]

            risk_cfg = RiskConfig(
                risk_per_trade=latest_intent["risk_per_trade"],
                max_position_pct=0.25,
                min_trade_value=15.0
            )
            risk_mgr = RiskManager(risk_cfg)
            pos_info = risk_mgr.calculate_position_size(
                equity=balance,
                entry_price=entry_price,
                stop_price=stop_price,
            )
            self.logger.info("RiskManager diagnostics: %s", pos_info)

            size = pos_info["size"] 
            if size > 0: 
                try: 
                    order = self.broker.place_order( self.symbol, side="buy", amount=size, price=entry_price, ) 
                    self.position = { "size": size, "entry_price": entry_price, "stop_price": stop_price, } 
                    self.logger.info( f"Entering LONG | price={entry_price} size={size} stop={stop_price} regime={latest['regime']}" ) 
                    self.heartbeat.beat( status="TRADING", details={ "symbol": self.symbol, "side": "buy", "price": order.get("price"), } ) 
                except Exception as e: 
                    self.alerts.send("CRITICAL", f"Order rejected: {e}") 
                    self.heartbeat.beat("ERROR", {"error": str(e)}) 
            else: 
                self.logger.warning( f"Trade rejected | reason={pos_info['reason']} entry={entry_price} stop={stop_price}" ) 
                self.heartbeat.beat("IDLE")

        # --- Exit logic ---
        pnl = None
        if self.position is not None:
            # Stop-loss check
            if latest["low"] <= self.position["stop_price"]:
                exit_price = self.position["stop_price"]
                pnl = (exit_price - self.position["entry_price"]) * self.position["size"]
                self.alerts.send("WARNING", f"Stop-loss triggered for {self.symbol} | pnl={pnl:.2f}")
                self.update_consecutive_losses(pnl)
                self.check_position_consistency()
                self.position = None

                # --- NEW: record trade --- 
                #trade_record = pd.DataFrame([{ "timestamp": latest.name, "pnl": pnl, "intent": latest_intent["intent"], "regime": latest["regime"] }])

                # --- NEW: set cooldown ---
                idx_pos = df.index.get_loc(latest.name)
                if idx_pos + self.cooldown_bars < len(df.index):
                    self.cooldown_until = df.index[idx_pos + self.cooldown_bars]

                self.heartbeat.beat("IDLE")
                #return trade_record

            # Flat intent check
            elif latest_intent["intent"] == TradeIntent.FLAT.value:
                exit_price = latest["close"]
                pnl = (exit_price - self.position["entry_price"]) * self.position["size"]
                self.logger.info(f"Exiting position | pnl={pnl:.2f}")
                self.update_consecutive_losses(pnl)
                self.check_position_consistency()
                self.position = None

                # --- NEW: record trade --- 
                #trade_record = pd.DataFrame([{ "timestamp": latest.name, "pnl": pnl, "intent": latest_intent["intent"], "regime": latest["regime"] }])

                self.heartbeat.beat("IDLE")
                #return trade_record

        trade_record = pd.DataFrame([{ "timestamp": pd.to_datetime(latest.name), "pnl": float(pnl) if pnl is not None else np.nan, "intent": str(latest_intent["intent"]), "regime": str(latest["regime"]) }])
        return trade_record

        
    def send_daily_summary(self, results_df):
        """Send daily PnL summary to Telegram at end of day."""
        today = datetime.datetime.utcnow().date()
        if "timestamp" not in results_df.columns or "pnl" not in results_df.columns:
            self.logger.warning("No results available for summary")
            return
        
        # Filter today's trades 
        todays_trades = results_df[results_df["timestamp"].dt.date == today]

        if todays_trades.empty: 
            self.logger.info("No trades today, skipping summary") 
            return

        pnl_today = todays_trades["pnl"].sum()
        win_rate = (todays_trades["pnl"] > 0).mean()

        # Optional Sharpe ratio if you have returns column 
        sharpe = None 
        if "returns" in todays_trades.columns: 
            mean_ret = todays_trades["returns"].mean() 
            std_ret = todays_trades["returns"].std() 
            if std_ret and std_ret > 0: 
                sharpe = (mean_ret / std_ret) * (252 ** 0.5) # annualized

        summary_msg = (
            f"📊 Daily Summary {today}\n"
            f"*Symbol:* {self.symbol}\n"
            f"*Timeframe:* {self.timeframe}\n"
            f"*Mode:* {self.mode}\n"
            f"PnL={pnl_today:.2f}\n"
            f"WinRate={win_rate:.2%}"
        )
        if sharpe is not None:
            summary_msg += f"\nSharpe={sharpe:.2f}"

        # Log locally 
        self.logger.info(summary_msg)

        self.alerts.send("INFO", summary_msg, include_info=True)

    def run(self):
        self.logger.info("Starting trading bot (paper mode)...")
        results_history = pd.DataFrame(columns=["timestamp", "pnl", "intent", "regime"])
        try:
            while True:
                try:
                    # 🔎 Heartbeat at start of cycle 
                    self.heartbeat.beat( 
                        status="RUNNING", 
                        details={ 
                            "mode": self.mode, 
                            "symbol": self.symbol, 
                            "timeframe": self.timeframe, 
                        }, 
                    )

                    # 🔎 Watchdog check 
                    if not self.check_heartbeat_freshness(): 
                        self.logger.error("Heartbeat watchdog triggered") 
                        raise SystemExit("Stale heartbeat detected")

                    trade_record = self.run_once()

                    if results_history.empty:
                        results_history = trade_record
                    else:
                        results_history = pd.concat([results_history, trade_record], ignore_index=True)

                    # Risk checks
                    self.check_daily_loss(results_history, threshold_pct=0.05)
                    self.check_position_consistency()

                    # 🔎 Scheduled daily summary check 
                    now = datetime.datetime.utcnow() 
                    if ( 
                        now.hour == self.summary_hour 
                        and now.minute == self.summary_minute 
                        and self.last_summary_date != now.date() 
                        ): 
                        self.send_daily_summary(results_history) 
                        self.last_summary_date = now.date()

                    results_history.to_csv("state/results_history.csv", index=False)

                    # 🔎 Maybe create backup
                    self.maybe_backup()

                except Exception as e:
                    self.logger.exception("Bot crashed during cycle")
                    self.heartbeat.beat("ERROR", {"error": str(e)})
                    self.alerts.send("CRITICAL", f"💥 {self.symbol} Bot crash: {e}")
                    raise  # re-raise to stop loop

                time.sleep(self.sleep_seconds)

        except KeyboardInterrupt:
            # Clean shutdown
            self.logger.info("Bot stopped by user")
            self.heartbeat.beat("STOPPED")
            self.alerts.send("INFO", f"🛑 {self.symbol} bot stopped by user", include_info=True)

        except SystemExit:
            # Explicit halt (e.g. drawdown guard)
            self.logger.warning("Bot halted by system exit")
            self.heartbeat.beat("STOPPED")
            self.alerts.send("CRITICAL", f"🛑 {self.symbol} bot halted due to safety condition")
            raise


import argparse

import argparse
import os
import time

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the trading bot")
    parser.add_argument(
        "--mode",
        choices=["paper", "sandbox", "live"],
        help="Override BOT_MODE (paper, sandbox, live)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Sleep interval between cycles in seconds (default: 60)",
    )
    args = parser.parse_args()

    # If CLI flag is set, override BOT_MODE environment variable
    if args.mode:
        os.environ["BOT_MODE"] = args.mode  # e.g. python trading_bot.py --mode paper

    # Initialize bot (no force_extreme_greed anymore)
    bot = TradingBot()

    try:
        bot.run()  # continuous run loop
    except KeyboardInterrupt:
        bot.logger.info("Bot stopped by user")
        bot.heartbeat.beat("STOPPED")
        bot.alerts.send("INFO", f"🛑 {bot.symbol} bot stopped by user", include_info=True)
    except Exception as e:
        bot.logger.exception("Bot crashed")
        bot.heartbeat.beat("ERROR", {"error": str(e)})
        bot.alerts.send("CRITICAL", f"🛑 {bot.symbol} bot halted due to safety condition")
        raise

