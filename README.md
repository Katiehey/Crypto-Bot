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

🐳 VS Code Docker Workflow Playbook
1. Start the bot
bash
docker compose up --build
Rebuilds image if needed and starts the trader container.

In VS Code, you can also use the Docker extension → right‑click docker-compose.yml → Compose Up.

2. Monitor logs continuously
All services logs (follow mode):

bash
docker compose logs -f
Trader service only:

bash
docker compose logs -f trader
In VS Code: open the integrated terminal and run the above, or use the Docker extension → right‑click container → View Logs.

3. Check health status
If you added a healthcheck in docker-compose.yml, run:

bash
docker inspect --format='{{json .State.Health}}' hybrid_crypto_bot
Quick check:

bash
docker ps
Look for healthy in the STATUS column.

4. Inspect trading logs
bash
docker compose exec trader tail -f /app/logs/trading_bot.log
Streams live trading activity.

For paper broker logs:

bash
docker compose exec trader tail -f /app/logs/paper_broker.log
5. Inspect state files
bash
docker compose exec trader ls -l /app/state
docker compose exec trader cat /app/state/heartbeat.json
Confirms heartbeat and equity snapshots are updating.

6. Simulate disaster recovery
bash
rm -rf state/
docker compose restart
./scripts/restore_backup.sh   # restores latest backup
docker compose restart
Then verify:

bash
ls -l state/
7. Cleanup when needed
bash
docker compose down.
docker system prune -f
Stops containers and removes unused images/volumes.

🎯 Monitoring Workflow in VS Code
Terminal Tabs:

Tab 1 → docker compose logs -f trader (continuous trading log).

Tab 2 → tail -f logs/trading_bot.log (host‑side synced log).

Tab 3 → watch ls -l state/ (see heartbeat and results update).

Docker Extension:

Right‑click container → Attach Shell to run health checks.

Right‑click container → View Logs for quick monitoring.

🐳 What Container Tools Gives You
Explorer view: A sidebar in VS Code showing your containers, images, volumes, and networks.

Context menus: Right‑click actions like Start, Stop, Attach Shell, View Logs.

File integration: Syntax highlighting, IntelliSense, and linting for Dockerfiles and docker-compose.yml.

Health & status checks: Quick visibility into whether containers are running and healthy.

✅ Typical Container Tools Actions in VS Code
Start services

Right‑click your docker-compose.yml → Compose Up.

Equivalent to docker compose up --build.

Stop services

Right‑click → Compose Down.

Equivalent to docker compose down.

View logs

In the Containers panel, right‑click your trader container → View Logs.

Equivalent to docker compose logs -f trader.

Attach shell

Right‑click container → Attach Shell.

Equivalent to docker compose exec trader bash.

Inspect state/volumes

Right‑click container → Inspect.

Lets you see mounts like /app/state, /app/backups, /app/logs.

🎯 Monitoring Workflow in VS Code
Run bot in paper mode

Use Compose Up from the extension.

Container Tools will show the container status.

Monitor trading logs continuously

Right‑click trader container → View Logs.

Keep this open while paper trading.

Check health

Hover over container in the sidebar → see status (running, healthy, etc.).

Or right‑click → Inspect for detailed health info.

Simulate disaster recovery

Use VS Code terminal:

bash
rm -rf state/
docker compose restart
./scripts/restore_backup.sh
docker compose restart
Then confirm restored files in the VS Code Explorer (state/ folder).

✅ How to Use .vscode/tasks.json in VS Code
Press Cmd+Shift+P (Mac) or Ctrl+Shift+P (Windows/Linux).

Type Run Task.

Pick one of your tasks:

Start Bot → builds and runs container.

Monitor Trader Logs → streams trading logs.

Check Health → prints container health status.

Simulate Disaster → deletes state/ and restarts container.

Restore Backup → restores latest backup and restarts container.

⚠️ Educational & research purposes only.
