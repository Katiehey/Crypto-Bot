# 🪙 Crypto-Bot

![Status](https://img.shields.io/badge/status-Paper%20Trading%20%E2%80%94%20Active-brightgreen)

A paper-trading orchestrator for cryptocurrency strategies.  
Crypto-Bot wires together **regime detection**, **strategy signals**, **risk management**, and a **paper broker** into a single loop that simulates live trading decisions.

---

## How It Works

The bot monitors the Bitcoin market every 4 hours, classifies whether the market is trending or moving sideways, and picks the most appropriate trading strategy for that condition. A risk manager sizes each position so a single losing trade never risks more than 1% of the account. All trades are simulated using real historical price data — no real money is involved until you explicitly switch to live mode.

---

## 🚀 Features

- **Regime Detection**: Classifies market state (TREND vs RANGE) using historical OHLCV data.
- **Strategies**:
  - Trend Following (refined)
  - Mean Reversion (refined)
  - Bollinger placeholder
- **Strategy Router**: Chooses intent (`LONG`, `FLAT`) based on regime, sentiment, and volume breakout filters.
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

```
src/
├── app/            # Orchestrator
├── backtest/       # Backtesting + metrics
├── engine/         # Strategy routing logic
├── execution/      # Broker abstraction
├── features/       # Technical indicators
├── regime/         # Market regime detection
├── risk/           # Capital allocation
├── strategies/     # Trading strategies
```

---

## ⚙️ Installation

Clone the repository:

```bash
git clone https://github.com/Katiehey/Crypto-Bot.git
cd Crypto-Bot
```

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate    # Mac/Linux
# .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

Copy the environment template and fill in your values:

```bash
cp .env.example .env
```

---

## ▶️ Usage

Run a single cycle:

```bash
python -m src.app.trading_bot
```

Force sentiment to Extreme Greed (for testing trades):

```bash
python -m src.app.trading_bot --force-greed
```

Run continuously (paper mode loop):

```python
bot = TradingBot(force_extreme_greed=False)
bot.run()
```

---

## 🐳 Docker

Build and start the trader container:

```bash
docker compose up --build
```

Stream all service logs:

```bash
docker compose logs -f
```

Trader service only:

```bash
docker compose logs -f trader
```

Check container health:

```bash
docker inspect --format='{{json .State.Health}}' hybrid_crypto_bot
docker ps
```

Inspect live trading logs:

```bash
docker compose exec trader tail -f /app/logs/trading_bot.log
docker compose exec trader tail -f /app/logs/paper_broker.log
```

Inspect state files:

```bash
docker compose exec trader ls -l /app/state
docker compose exec trader cat /app/state/heartbeat.json
```

Simulate disaster recovery:

```bash
rm -rf state/
docker compose restart
./scripts/restore_backup.sh
docker compose restart
```

Teardown:

```bash
docker compose down
docker system prune -f
```

---

## 🎯 Monitoring (VS Code)

Open three terminal tabs for live visibility:

| Tab | Command | Purpose |
|-----|---------|---------|
| 1 | `docker compose logs -f trader` | Continuous trading log |
| 2 | `tail -f logs/trading_bot.log` | Host-side synced log |
| 3 | `watch ls -l state/` | Heartbeat and results updates |

Using the VS Code Docker extension: right-click the container → **Attach Shell** for interactive access, or **View Logs** for quick monitoring.

---

> ⚠️ Educational and research purposes only. Not financial advice.
