from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config import ExecutionConfig, RiskConfig
from ..domain import BookSnapshot, ClosedTrade, Direction, Fill, Order, OrderType, Position, Side, TradingSignal
from ..paths import DATA_DIR
from .simulator import QueueAwareFillModel

logger = logging.getLogger(__name__)


class PaperBroker:
    def __init__(
        self,
        execution: ExecutionConfig,
        risk: RiskConfig,
        state_path: Path | None = None,
        restore: bool = True,
    ) -> None:
        self.execution = execution
        self.risk = risk
        self.fill_model = QueueAwareFillModel(execution)
        self.state_path = state_path or (DATA_DIR / "paper_state.json")
        self.balance = float(risk.initial_balance)
        self.peak_balance = self.balance
        self.position: Position | None = None
        self.pending_orders: dict[str, Order] = {}
        self.trades: list[ClosedTrade] = []
        self.fills: list[Fill] = []
        self.last_price = 0.0
        self.last_regime = "RANGE"
        self.last_event = "Ожидание"
        if restore:
            self.load_state()

    def reset(self) -> None:
        self.balance = float(self.risk.initial_balance)
        self.peak_balance = self.balance
        self.position = None
        self.pending_orders.clear()
        self.trades.clear()
        self.fills.clear()
        self.last_price = 0.0
        self.last_event = "Состояние сброшено"
        self.save_state()

    @property
    def equity(self) -> float:
        if not self.position or self.last_price <= 0:
            return self.balance
        if self.position.direction == Direction.LONG:
            unrealized = (self.last_price - self.position.entry_price) * self.position.quantity
        else:
            unrealized = (self.position.entry_price - self.last_price) * self.position.quantity
        return self.balance + unrealized

    @property
    def unrealized_pnl(self) -> float:
        return self.equity - self.balance

    def open_positions_count(self) -> int:
        return 1 if self.position else 0

    def submit_signal(self, signal: TradingSignal, quantity: float, snapshot: BookSnapshot) -> Order | None:
        if self.position or self.pending_orders or signal.direction == Direction.FLAT or quantity <= 0:
            return None
        side = Side.BUY if signal.direction == Direction.LONG else Side.SELL
        order = self.fill_model.create_order(signal.id, signal.symbol, side, signal.order_type, quantity, snapshot)
        self.pending_orders[order.id] = order
        self.last_regime = signal.regime
        self.last_event = f"Заявка {side.value} создана"
        self.save_state()
        return order

    def _open_from_fill(self, order: Order, fill: Fill, snapshot: BookSnapshot) -> None:
        direction = Direction.LONG if fill.side == Side.BUY else Direction.SHORT
        entry = fill.price
        stop_delta = entry * self.risk.stop_loss_bps / 10_000.0
        tp_delta = entry * self.risk.take_profit_bps / 10_000.0
        stop = entry - stop_delta if direction == Direction.LONG else entry + stop_delta
        take = entry + tp_delta if direction == Direction.LONG else entry - tp_delta
        self.position = Position(
            symbol=order.symbol,
            direction=direction,
            quantity=fill.quantity,
            entry_price=entry,
            opened_ts_ms=fill.ts_ms,
            stop_price=stop,
            take_profit_price=take,
            trailing_anchor=entry,
            fees=fill.fee,
            signal_id=order.signal_id,
        )
        self.balance -= fill.fee
        self.last_event = f"Открыта {direction.value} по {entry:.4f}"
        logger.info(self.last_event)

    def _position_exit_price(self, snapshot: BookSnapshot) -> float:
        if not self.position:
            return snapshot.mid
        side = Side.SELL if self.position.direction == Direction.LONG else Side.BUY
        price, _ = self.fill_model._market_fill_price(side, self.position.quantity, snapshot)
        return price

    def close_position(self, snapshot: BookSnapshot, reason: str) -> ClosedTrade | None:
        position = self.position
        if not position:
            return None
        exit_price = self._position_exit_price(snapshot)
        exit_side = Side.SELL if position.direction == Direction.LONG else Side.BUY
        exit_fee = exit_price * position.quantity * self.execution.taker_fee_bps / 10_000.0
        gross = (
            (exit_price - position.entry_price) * position.quantity
            if position.direction == Direction.LONG
            else (position.entry_price - exit_price) * position.quantity
        )
        fees = position.fees + exit_fee
        # Entry fee was already deducted from balance when the position opened.
        # Reported trade PnL must nevertheless include both entry and exit fees.
        net = gross - fees
        self.balance += gross - exit_fee
        self.peak_balance = max(self.peak_balance, self.balance)
        denominator = max(position.entry_price * position.quantity, 1e-9)
        trade = ClosedTrade(
            id=uuid.uuid4().hex,
            signal_id=position.signal_id,
            symbol=position.symbol,
            direction=position.direction,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            opened_ts_ms=position.opened_ts_ms,
            closed_ts_ms=snapshot.local_ts_ms,
            gross_pnl=gross,
            fees=fees,
            net_pnl=net,
            return_pct=net / denominator * 100.0,
            reason=reason,
            regime=self.last_regime,
        )
        self.trades.append(trade)
        self.trades = self.trades[-2000:]
        self.position = None
        self.last_event = f"Позиция закрыта: {reason}, PnL {net:+.2f}"
        logger.info(self.last_event)
        self.save_state()
        return trade

    def _manage_position(self, snapshot: BookSnapshot) -> ClosedTrade | None:
        position = self.position
        if not position:
            return None
        mid = snapshot.mid
        if position.direction == Direction.LONG:
            position.trailing_anchor = max(position.trailing_anchor, mid)
            activation = position.entry_price * (1 + self.risk.trailing_activation_bps / 10_000.0)
            if position.trailing_anchor >= activation:
                trail = position.trailing_anchor * (1 - self.risk.trailing_distance_bps / 10_000.0)
                position.stop_price = max(position.stop_price, trail)
            if snapshot.best_bid <= position.stop_price:
                return self.close_position(snapshot, "STOP/TRAILING")
            if snapshot.best_bid >= position.take_profit_price:
                return self.close_position(snapshot, "TAKE_PROFIT")
        else:
            position.trailing_anchor = min(position.trailing_anchor, mid)
            activation = position.entry_price * (1 - self.risk.trailing_activation_bps / 10_000.0)
            if position.trailing_anchor <= activation:
                trail = position.trailing_anchor * (1 + self.risk.trailing_distance_bps / 10_000.0)
                position.stop_price = min(position.stop_price, trail)
            if snapshot.best_ask >= position.stop_price:
                return self.close_position(snapshot, "STOP/TRAILING")
            if snapshot.best_ask <= position.take_profit_price:
                return self.close_position(snapshot, "TAKE_PROFIT")
        if snapshot.local_ts_ms - position.opened_ts_ms >= self.risk.max_holding_seconds * 1000:
            return self.close_position(snapshot, "MAX_HOLD_TIME")
        return None

    def on_snapshot(self, snapshot: BookSnapshot) -> list[ClosedTrade]:
        self.last_price = snapshot.mid
        closed: list[ClosedTrade] = []
        for order_id, order in list(self.pending_orders.items()):
            result = self.fill_model.process(order, snapshot)
            if result.fill:
                self.fills.append(result.fill)
                if order.status == "FILLED":
                    self.pending_orders.pop(order_id, None)
                    self._open_from_fill(order, result.fill, snapshot)
            elif result.cancelled:
                self.pending_orders.pop(order_id, None)
                self.last_event = f"Заявка отменена: {result.reason}"
        trade = self._manage_position(snapshot)
        if trade:
            closed.append(trade)
        self.peak_balance = max(self.peak_balance, self.equity)
        return closed

    def save_state(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "balance": self.balance,
            "peak_balance": self.peak_balance,
            "position": asdict(self.position) if self.position else None,
            "pending_orders": [asdict(order) for order in self.pending_orders.values()],
            "trades": [trade.to_dict() for trade in self.trades[-500:]],
            "last_event": self.last_event,
        }
        if payload["position"]:
            payload["position"]["direction"] = self.position.direction.value  # type: ignore[index,union-attr]
        for row, order in zip(payload["pending_orders"], self.pending_orders.values(), strict=False):
            row["side"] = order.side.value
            row["order_type"] = order.order_type.value
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.state_path)

    def load_state(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        try:
            self.balance = float(payload.get("balance", self.balance))
            self.peak_balance = max(float(payload.get("peak_balance", self.balance)), self.balance)
            position = payload.get("position")
            if isinstance(position, dict):
                position["direction"] = Direction(position["direction"])
                self.position = Position(**position)
            self.trades = []
            for row in payload.get("trades", []):
                if not isinstance(row, dict):
                    continue
                row["direction"] = Direction(row["direction"])
                self.trades.append(ClosedTrade(**row))
            self.last_event = str(payload.get("last_event", "Состояние восстановлено"))
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("Paper state recovery failed: %s", exc)
            self.position = None
            self.pending_orders.clear()

    def status(self) -> dict[str, Any]:
        position = asdict(self.position) if self.position else None
        if position:
            position["direction"] = self.position.direction.value
            position["unrealized_pnl"] = self.unrealized_pnl
        return {
            "balance": self.balance,
            "equity": self.equity,
            "peak_balance": self.peak_balance,
            "unrealized_pnl": self.unrealized_pnl,
            "position": position,
            "pending_orders": len(self.pending_orders),
            "trade_count": len(self.trades),
            "last_event": self.last_event,
        }
