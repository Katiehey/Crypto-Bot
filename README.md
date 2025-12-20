# 🪙 Crypto-Bot

A paper‑trading orchestrator for cryptocurrency strategies.  
Crypto‑Bot wires together **regime detection**, **strategy signals**, **risk management**, and a **paper broker** into a single loop that simulates live trading decisions.

---

## 🚀 Features

- **Regime Detection**: Classifies market state (TREND vs RANGE) using historical OHLCV data.
- **Strategies**:
  - Trend Following (refined)
  - Mean Reversion (refined)
  - Bollinger placeholder 
- **Strategy Router (refined)**: Chooses intent (`LONG`, `FLAT`) based on regime, sentiment, and volume breakout filters.
- **Risk Manager**: Sizes positions safely with:
  - Risk per trade (% of equity)
  - Max position cap (% of equity)
  - Minimum trade value enforcement
- **Paper Broker**: Simulates orders and balance without touching a real exchange.
- **Orchestrator**:
  - One symbol per loop
  - One position at a time
  - Safe restarts (stateless per run)
  - Deterministic behavior
  - Runs on schedule (default: every 4 hours)

---

## 📂 Project Structure

src/
├── app/            # Orchestrator
├── backtest/       # Backtesting + metrics
├── engine/         # Strategy routing logic
├── execution/      # Broker abstraction
├── features/       # Technical indicators
├── regime/         # Market regime detection
├── risk/           # Capital allocation
├── strategies/     # Trading strategies

---

## ⚙️ Installation

```bash
# Clone repo
git clone https://github.com/yourusername/Crypto-Bot.git
cd Crypto-Bot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

## Run a single cycle:
python -m src.app.trading_bot

## Force sentiment to Extreme Greed (for testing trades):
python -m src.app.trading_bot --force-greed

## Run continuously (production loop):
bot = TradingBot(force_extreme_greed=False)
bot.run()



⚠️ Educational & research purposes only.
