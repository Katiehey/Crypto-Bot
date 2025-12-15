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
