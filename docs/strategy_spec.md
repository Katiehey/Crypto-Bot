# Strategy Specification v1

## Objective
Build a regime-aware crypto trading bot optimized for capital preservation and steady compounding.

## Assets
- BTC/USDT (initial)

## Market
- Spot trading

## Timeframes
- Primary: 4H
- Confirmation: 1D

## Strategy Overview
- Trend-following strategy using moving average crossovers during trending regimes
- Mean-reversion strategy using RSI and Bollinger Bands during ranging regimes
- A regime detection module selects the active strategy

## Direction
- Long-only

## Execution Frequency
- Medium-term (4H / 1D candles)


## Risk Management

- Risk per trade: max 1% of total equity
- Stop-loss: ATR-based dynamic stop
- Maximum drawdown allowed: 20%
- Maximum open positions: 1
- Kill-switch activated if daily loss exceeds 3%

## Performance Targets

- Sharpe Ratio >= 1.2
- Positive expectancy
- Lower drawdown than BTC buy-and-hold
