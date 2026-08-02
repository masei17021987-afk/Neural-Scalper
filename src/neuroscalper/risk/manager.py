from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import ExecutionConfig, ModelConfig, RiskConfig
from ..domain import BookSnapshot, Direction, RiskDecision, TradingSignal


@dataclass(slots=True)
class RiskState:
    balance: float
    equity: float
    peak_equity: float
    daily_start_equity: float
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    last_trade_close_ts_ms: int = 0
    kill_switch: bool = False
    kill_reason: str = ""
    date_utc: str = ""


class RiskManager:
    def __init__(self, risk: RiskConfig, execution: ExecutionConfig, model: ModelConfig) -> None:
        self.config = risk
        self.execution = execution
        self.model = model
        initial = float(risk.initial_balance)
        self.state = RiskState(initial, initial, initial, initial, date_utc=self._today())

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def sync_equity(self, balance: float, equity: float) -> None:
        if self.state.date_utc != self._today():
            self.state.date_utc = self._today()
            self.state.daily_start_equity = equity
            self.state.daily_realized_pnl = 0.0
        self.state.balance = float(balance)
        self.state.equity = float(equity)
        self.state.peak_equity = max(self.state.peak_equity, self.state.equity, self.state.balance)
        self._check_global_limits()

    def _check_global_limits(self) -> None:
        drawdown = 1.0 - self.state.equity / max(self.state.peak_equity, 1e-9)
        daily_loss = max(0.0, self.state.daily_start_equity - self.state.equity)
        if drawdown >= self.config.max_drawdown_pct / 100.0:
            self.trigger_kill("MAX_DRAWDOWN", "Достигнут максимальный спад от пика капитала.")
        if daily_loss >= self.state.daily_start_equity * self.config.max_daily_loss_pct / 100.0:
            self.trigger_kill("MAX_DAILY_LOSS", "Достигнут дневной лимит убытка.")

    def trigger_kill(self, code: str, message: str) -> None:
        self.state.kill_switch = True
        self.state.kill_reason = f"{code}: {message}"

    def reset_kill_switch(self) -> None:
        self.state.kill_switch = False
        self.state.kill_reason = ""
        self.state.consecutive_losses = 0
        self.state.peak_equity = max(self.state.peak_equity, self.state.equity)

    def evaluate(
        self,
        signal: TradingSignal,
        snapshot: BookSnapshot,
        open_positions: int,
        router_size_multiplier: float = 1.0,
        check_staleness: bool = True,
    ) -> RiskDecision:
        # Cooldowns follow event time, so the same guard works in live feeds and deterministic replay.
        now_ms = int(snapshot.local_ts_ms)
        wall_now_ms = int(time.time() * 1000)
        self._check_global_limits()
        if signal.direction == Direction.FLAT:
            return RiskDecision(False, "FLAT", "Нейросеть не видит достаточного преимущества.")
        if self.state.kill_switch:
            return RiskDecision(False, "KILL_SWITCH", self.state.kill_reason or "Торговля остановлена защитой.")
        age_ms = max(0, wall_now_ms - snapshot.local_ts_ms)
        if check_staleness and age_ms > 2500:
            return RiskDecision(False, "STALE_DATA", "Рыночные данные устарели; вход отменён.", {"age_ms": age_ms})
        if snapshot.spread_bps > self.execution.max_spread_bps:
            return RiskDecision(
                False, "SPREAD_TOO_WIDE", "Спред слишком широкий — комиссия и проскальзывание съедят преимущество.",
                {"spread_bps": snapshot.spread_bps, "limit_bps": self.execution.max_spread_bps},
            )
        if signal.confidence < self.model.min_confidence:
            return RiskDecision(False, "LOW_CONFIDENCE", "Уверенность модели ниже безопасного порога.")
        if signal.expected_net_edge_bps < self.model.min_net_edge_bps:
            return RiskDecision(False, "NO_NET_EDGE", "После комиссий ожидаемого преимущества недостаточно.")
        if open_positions >= self.config.max_open_positions:
            return RiskDecision(False, "MAX_POSITIONS", "Уже открыт максимально допустимый объём позиций.")
        if router_size_multiplier <= 0:
            return RiskDecision(False, "REGIME_BLOCK", "Текущий режим рынка запрещает новые входы.")
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            elapsed = (now_ms - self.state.last_trade_close_ts_ms) / 1000.0
            if elapsed < max(60, self.config.cooldown_seconds * 5):
                return RiskDecision(False, "LOSS_STREAK", "После серии убытков включена увеличенная пауза.")
        if self.state.last_trade_close_ts_ms:
            elapsed = (now_ms - self.state.last_trade_close_ts_ms) / 1000.0
            if elapsed < self.config.cooldown_seconds:
                return RiskDecision(False, "COOLDOWN", "После сделки действует короткая пауза.", {"seconds_left": self.config.cooldown_seconds - elapsed})
        return RiskDecision(True, "OK", "Все ограничения риска пройдены.")

    def position_size(self, price: float, size_multiplier: float = 1.0) -> float:
        if price <= 0:
            return 0.0
        risk_budget = self.state.equity * self.config.risk_per_trade_pct / 100.0
        stop_distance = price * self.config.stop_loss_bps / 10_000.0
        quantity_by_risk = risk_budget / max(stop_distance, price * 1e-6)
        max_notional = self.state.equity * self.config.max_position_notional_pct / 100.0
        quantity_by_notional = max_notional / price
        return max(0.0, min(quantity_by_risk, quantity_by_notional) * max(0.0, size_multiplier))

    def record_closed_trade(self, net_pnl: float, closed_ts_ms: int | None = None) -> None:
        self.state.daily_realized_pnl += float(net_pnl)
        self.state.last_trade_close_ts_ms = int(closed_ts_ms or time.time() * 1000)
        if net_pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def status(self) -> dict[str, Any]:
        drawdown_pct = max(0.0, (1.0 - self.state.equity / max(self.state.peak_equity, 1e-9)) * 100.0)
        daily_pnl = self.state.equity - self.state.daily_start_equity
        return {
            "balance": self.state.balance,
            "equity": self.state.equity,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": drawdown_pct,
            "daily_pnl": daily_pnl,
            "consecutive_losses": self.state.consecutive_losses,
            "kill_switch": self.state.kill_switch,
            "kill_reason": self.state.kill_reason,
            "limits": {
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "max_daily_loss_pct": self.config.max_daily_loss_pct,
                "risk_per_trade_pct": self.config.risk_per_trade_pct,
            },
        }
