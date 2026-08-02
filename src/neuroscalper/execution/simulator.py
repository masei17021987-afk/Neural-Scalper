from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from ..config import ExecutionConfig
from ..domain import BookSnapshot, Fill, Order, OrderType, Side


@dataclass(slots=True)
class FillResult:
    fill: Fill | None = None
    cancelled: bool = False
    reason: str = ""


class QueueAwareFillModel:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self._last_trade_seen: dict[str, tuple[int, float | None, float]] = {}

    def create_order(
        self,
        signal_id: str,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: float,
        snapshot: BookSnapshot,
    ) -> Order:
        now = snapshot.local_ts_ms
        price: float | None = None
        queue_ahead = 0.0
        if order_type in {OrderType.LIMIT, OrderType.POST_ONLY}:
            if side == Side.BUY:
                price = snapshot.best_bid
                queue_ahead = snapshot.bids[0].quantity * self.config.queue_factor if snapshot.bids else 0.0
            else:
                price = snapshot.best_ask
                queue_ahead = snapshot.asks[0].quantity * self.config.queue_factor if snapshot.asks else 0.0
        return Order(
            id=uuid.uuid4().hex,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=max(0.0, quantity),
            price=price,
            created_ts_ms=now,
            active_ts_ms=now + self.config.assumed_latency_ms,
            cancel_ts_ms=(now + self.config.assumed_latency_ms + self.config.cancel_after_ms) if price else None,
            queue_ahead=max(0.0, queue_ahead),
        )

    def _market_fill_price(self, side: Side, quantity: float, snapshot: BookSnapshot) -> tuple[float, float]:
        levels = snapshot.asks if side == Side.BUY else snapshot.bids
        remaining = max(0.0, quantity)
        notional = 0.0
        filled = 0.0
        for level in levels:
            take = min(remaining, max(0.0, level.quantity))
            if take <= 0:
                continue
            notional += take * level.price
            filled += take
            remaining -= take
            if remaining <= 1e-12:
                break
        if filled < quantity and levels:
            fallback = levels[-1].price
            notional += (quantity - filled) * fallback
            filled = quantity
        average = notional / filled if filled else snapshot.mid
        slip = self.config.slippage_bps / 10_000.0
        average *= 1.0 + slip if side == Side.BUY else 1.0 - slip
        return average, filled

    def market_fill(self, order: Order, snapshot: BookSnapshot) -> FillResult:
        if snapshot.local_ts_ms < order.active_ts_ms:
            return FillResult(reason="latency")
        price, quantity = self._market_fill_price(order.side, order.quantity, snapshot)
        if quantity <= 0:
            return FillResult(cancelled=True, reason="empty_book")
        fee = price * quantity * self.config.taker_fee_bps / 10_000.0
        order.filled_quantity = quantity
        order.average_fill_price = price
        order.status = "FILLED"
        return FillResult(
            fill=Fill(uuid.uuid4().hex, order.id, order.symbol, order.side, quantity, price, fee, snapshot.local_ts_ms, "TAKER")
        )

    def process_limit(self, order: Order, snapshot: BookSnapshot) -> FillResult:
        now = snapshot.local_ts_ms
        if now < order.active_ts_ms:
            return FillResult(reason="latency")
        if order.cancel_ts_ms is not None and now >= order.cancel_ts_ms:
            order.status = "CANCELLED"
            return FillResult(cancelled=True, reason="timeout")
        if order.price is None or snapshot.last_trade_price is None:
            return FillResult(reason="waiting_trade")

        trade_key = (snapshot.last_trade_ts_ms, snapshot.last_trade_price, snapshot.last_trade_quantity)
        if self._last_trade_seen.get(order.id) == trade_key:
            return FillResult(reason="duplicate_trade")
        self._last_trade_seen[order.id] = trade_key

        aggressive_sell = bool(snapshot.buyer_is_maker)
        crossed = (
            order.side == Side.BUY and aggressive_sell and snapshot.last_trade_price <= order.price
        ) or (
            order.side == Side.SELL and not aggressive_sell and snapshot.last_trade_price >= order.price
        )
        if not crossed:
            return FillResult(reason="not_crossed")

        traded_quantity = max(0.0, snapshot.last_trade_quantity)
        if order.queue_ahead > 0:
            consumed = min(order.queue_ahead, traded_quantity)
            order.queue_ahead -= consumed
            traded_quantity -= consumed
        if traded_quantity <= 0:
            order.status = "OPEN"
            return FillResult(reason="queue_ahead")
        # MVP execution uses an atomic resting-order fill once queue priority has
        # been earned. This is intentionally conservative about *whether* a fill
        # happens, while avoiding an unsafe half-position state in the paper broker.
        remaining = order.quantity - order.filled_quantity
        fill_qty = max(0.0, remaining)
        if fill_qty <= 0:
            return FillResult(reason="filled")
        order.filled_quantity = order.quantity
        order.average_fill_price = order.price
        order.status = "FILLED"
        fee = order.price * fill_qty * self.config.maker_fee_bps / 10_000.0
        return FillResult(
            fill=Fill(uuid.uuid4().hex, order.id, order.symbol, order.side, fill_qty, order.price, fee, now, "MAKER")
        )

    def process(self, order: Order, snapshot: BookSnapshot) -> FillResult:
        if order.order_type == OrderType.MARKET:
            return self.market_fill(order, snapshot)
        return self.process_limit(order, snapshot)
