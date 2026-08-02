from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from ..domain import ClosedTrade


def _finite(value: float) -> float:
    return float(value) if math.isfinite(value) else 0.0


def summarize_performance(
    trades: Iterable[ClosedTrade],
    equity_curve: list[tuple[int, float]],
    initial_balance: float,
    signals: int,
    orders: int,
    fills: int,
    rejected: int,
) -> dict[str, float | int]:
    trade_list = list(trades)
    wins = [trade for trade in trade_list if trade.net_pnl > 0]
    losses = [trade for trade in trade_list if trade.net_pnl < 0]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    final_equity = equity_curve[-1][1] if equity_curve else initial_balance
    net_profit = final_equity - initial_balance

    values = np.asarray([value for _, value in equity_curve], dtype=np.float64)
    max_drawdown_pct = 0.0
    if len(values):
        peaks = np.maximum.accumulate(values)
        drawdowns = 1.0 - np.divide(values, np.maximum(peaks, 1e-12))
        max_drawdown_pct = float(np.max(drawdowns) * 100.0)

    returns = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0:
            returns.append((current / previous) - 1.0)
    return_array = np.asarray(returns, dtype=np.float64)
    sharpe = 0.0
    sortino = 0.0
    if len(return_array) > 2 and float(np.std(return_array)) > 1e-12:
        sharpe = float(np.mean(return_array) / np.std(return_array) * math.sqrt(len(return_array)))
        downside = return_array[return_array < 0]
        if len(downside) and float(np.std(downside)) > 1e-12:
            sortino = float(np.mean(return_array) / np.std(downside) * math.sqrt(len(return_array)))

    average_win = gross_profit / len(wins) if wins else 0.0
    average_loss = gross_loss / len(losses) if losses else 0.0
    expectancy = sum(trade.net_pnl for trade in trade_list) / len(trade_list) if trade_list else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-12 else (gross_profit if gross_profit else 0.0)
    return {
        "initial_balance": round(initial_balance, 4),
        "final_equity": round(final_equity, 4),
        "net_profit": round(net_profit, 4),
        "return_pct": round(net_profit / max(initial_balance, 1e-12) * 100.0, 4),
        "trades": len(trade_list),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trade_list) * 100.0, 3) if trade_list else 0.0,
        "profit_factor": round(_finite(profit_factor), 4),
        "expectancy": round(expectancy, 6),
        "average_win": round(average_win, 6),
        "average_loss": round(average_loss, 6),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "sharpe_proxy": round(_finite(sharpe), 4),
        "sortino_proxy": round(_finite(sortino), 4),
        "signals": int(signals),
        "orders": int(orders),
        "fills": int(fills),
        "rejected_signals": int(rejected),
        "fill_rate_pct": round(fills / max(orders, 1) * 100.0, 3),
    }
