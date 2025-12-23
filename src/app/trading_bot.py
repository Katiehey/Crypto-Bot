import os
import time
import pandas as pd
import datetime
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



class TradingBot:
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1d",
        sleep_seconds: int = 60 * 60 * 4,  # 4H
        force_extreme_greed: bool = False,
        cooldown_bars: int = 1,  # number of bars to cooldown after stop-loss
    ):
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

        if self.mode == "paper": 
            self.broker = PaperBroker( 
                starting_balance=self.config["risk"].get("starting_balance", 500.0), 
                data_path=self.config["exchange"].get("data_path", "data/btc_usdt_features.csv"), 
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
        self.broker = PaperBroker()
        self.regime_detector = RegimeDetector()
        self.trend_strategy = TrendFollowingStrategy()
        self.mr_strategy = MeanReversionStrategy()
        self.router = StrategyRouter()

        self.position = None
        self.starting_equity = self.broker.get_balance()["USDT"]

        # Monitoring
        self.logger = setup_logger("TradingBot", "trading_bot.log")
        self.alerts = AlertManager(self.logger)

        self.logger.info("Bot initialized | symbol=%s timeframe=%s", self.symbol, self.timeframe)

        # Track last summary date
        self.last_summary_date = None

    def check_daily_loss(self, results_df, threshold_pct=0.05):
        today = datetime.datetime.utcnow().date()
        pnl_today = results_df[results_df["timestamp"].dt.date == today]["pnl"].sum()
        if pnl_today < -threshold_pct * self.starting_equity:
            self.alerts.send("CRITICAL", f"Daily loss exceeded {threshold_pct*100:.0f}%. Bot halted.")
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

    def run_once(self):
        self.logger.info("Fetching market data...")
        try:
            df = self.broker.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
        except Exception as e:
            self.alerts.send("CRITICAL", f"Exchange connection failure: {e}")
            raise

        # --- Regime Detection ---
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
        boll_signals = pd.DataFrame({
            "signal": [None] * len(df),
            "stop_price": [None] * len(df),
        }, index=df.index)

        # --- Route Intent ---
        intent_df = self.router.route(df, trend_signals, mr_signals, boll_signals)

        latest = df.iloc[-1]
        latest_intent = intent_df.iloc[-1]

        self.logger.info(
            f"Regime={latest['regime']} | Intent={latest_intent['intent']} | "
            f"TrendSignal={trend_signals.iloc[-1]['signal']} | "
            f"Volume={latest['volume']} vs avg={df['volume'].rolling(20).mean().iloc[-1]}"
        )

        # --- Position Handling ---
        balance = self.broker.get_balance()["USDT"]

        # Drawdown guard
        if balance < self.starting_equity * 0.8:
            self.alerts.send("CRITICAL", "Equity drawdown exceeded 20%. Bot halted.")
            raise SystemExit()
        
        latest = df.iloc[-1]

        # --- Cooldown guard --- 
        if self.cooldown_until and latest.name <= self.cooldown_until: 
            self.logger.info("Cooldown active, skipping trades") 
            return intent_df

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
                    self.broker.place_order(
                        self.symbol,
                        side="buy",
                        amount=size,
                        price=entry_price,
                    )
                    self.position = {
                        "size": size,
                        "entry_price": entry_price,
                        "stop_price": stop_price,
                    }
                    self.logger.info(
                        f"Entering LONG | price={entry_price} size={size} stop={stop_price} regime={latest['regime']}"
                    )
                except Exception as e:
                    self.alerts.send("CRITICAL", f"Order rejected: {e}")
            else:
                self.logger.warning(
                    f"Trade rejected | reason={pos_info['reason']} entry={entry_price} stop={stop_price}"
                )

        # --- Exit logic (example stop-loss + flat intent) --- 
        if self.position is not None: 
            # Stop-loss check 
            if latest["low"] <= self.position["stop_price"]: 
                exit_price = self.position["stop_price"] 
                pnl = (exit_price - self.position["entry_price"]) * self.position["size"] 
                self.alerts.send("WARNING", f"Stop-loss triggered for {self.symbol} | pnl={pnl:.2f}") 
                # Kill switch checks 
                self.update_consecutive_losses(pnl) 
                self.check_position_consistency() 
                self.position = None 

                # --- NEW: set cooldown (configurable bars) --- 
                idx_pos = df.index.get_loc(latest.name) 
                if idx_pos + self.cooldown_bars < len(df.index): 
                    self.cooldown_until = df.index[idx_pos + self.cooldown_bars]

            # Flat intent check 
            elif latest_intent["intent"] == TradeIntent.FLAT.value: 
                exit_price = latest["close"] 
                pnl = (exit_price - self.position["entry_price"]) * self.position["size"] 
                self.logger.info(f"Exiting position | pnl={pnl:.2f}") 
                # Kill switch checks 
                self.update_consecutive_losses(pnl) 
                self.check_position_consistency() 
                self.position = None

        return intent_df  # return intents for summary

    def send_daily_summary(self, results_df):
        """Send daily PnL summary to Telegram at end of day."""
        today = datetime.datetime.utcnow().date()
        if "timestamp" not in results_df.columns or "pnl" not in results_df.columns:
            self.logger.warning("No results available for summary")
            return

        pnl_today = results_df[results_df["timestamp"].dt.date == today]["pnl"].sum()
        win_rate = (results_df[results_df["timestamp"].dt.date == today]["pnl"] > 0).mean()

        summary_msg = (
            f"📊 Daily Summary {today}\n"
            f"PnL={pnl_today:.2f}\n"
            f"WinRate={win_rate:.2%}"
        )
        self.alerts.send("INFO", summary_msg)

    def run(self):
        self.logger.info("Starting trading bot (paper mode)...")
        while True:
            try:
                results = self.run_once()
                self.check_daily_loss(results, threshold_pct=0.05)
                self.check_position_consistency()
                # Daily summary check
                today = datetime.datetime.utcnow().date()
                if self.last_summary_date != today:
                    self.send_daily_summary(results)
                    self.last_summary_date = today
            except Exception as e:
                self.alerts.send("CRITICAL", f"Bot crash: {e}")
                raise
            time.sleep(self.sleep_seconds)


import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the trading bot in paper mode")
    parser.add_argument( 
        "--mode", 
        choices=["paper", "sandbox", "live"], 
        help="Override BOT_MODE (paper, sandbox, live)", 
    )
    parser.add_argument(
        "--force-greed",
        action="store_true",
        help="Force sentiment to Extreme Greed (>=0.75) for testing trades",
    )
    args = parser.parse_args()

    # If CLI flag is set, override BOT_MODE environment variable 
    if args.mode: 
        os.environ["BOT_MODE"] = args.mode#e.g python trading_bot.py --mode paper


    bot = TradingBot(force_extreme_greed=args.force_greed)
    bot.run_once()  # run a single cycle for testing
