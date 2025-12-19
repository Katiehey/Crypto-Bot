import numpy as np
import pandas as pd

def calculate_cagr(equity: pd.Series, periods_per_year: int = 252) -> float:
    """Compound Annual Growth Rate (CAGR)."""
    if equity.empty:
        return 0.0

    # Case 1: DatetimeIndex
    if isinstance(equity.index, pd.DatetimeIndex):
        total_years = (equity.index[-1] - equity.index[0]).days / 365.25
    else:
        # Case 2: integer index, assume daily data
        total_years = len(equity) / periods_per_year

    if total_years <= 0:
        return 0.0

    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / total_years) - 1



def calculate_drawdown(equity: pd.Series) -> pd.DataFrame:
    """Drawdown series and max drawdown."""
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return pd.DataFrame({
        "drawdown": drawdown,
        "max_drawdown": drawdown.min()
    })


def calculate_sharpe(equity: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    returns = equity.pct_change().dropna()
    excess_returns = returns - risk_free_rate / 252
    if returns.std() == 0:
        return 0.0
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()


def trade_statistics(trades: pd.DataFrame) -> dict:
    """Basic trade stats: win rate, expectancy, avg win/loss."""
    if trades.empty:
        return {}

    wins = trades[trades["pnl_pct"] > 0]
    losses = trades[trades["pnl_pct"] <= 0]

    win_rate = len(wins) / len(trades)
    avg_win = wins["pnl_pct"].mean() if not wins.empty else 0.0
    avg_loss = losses["pnl_pct"].mean() if not losses.empty else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    return {
        "total_trades": len(trades),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
    }

def calculate_sortino(equity: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sortino ratio (downside risk only)."""
    returns = equity.pct_change().dropna()
    excess_returns = returns - risk_free_rate / 252
    downside = excess_returns[excess_returns < 0]
    if downside.std() == 0:
        return 0.0
    return np.sqrt(252) * excess_returns.mean() / downside.std()


def calculate_calmar(equity: pd.Series) -> float:
    """Calmar ratio = CAGR / Max Drawdown."""
    cagr = calculate_cagr(equity)
    max_dd = calculate_drawdown(equity)["max_drawdown"].iloc[-1]
    if max_dd == 0:
        return 0.0
    return cagr / abs(max_dd)
