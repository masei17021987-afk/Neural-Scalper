from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from ..domain import BookLevel, BookSnapshot


class OrderBookGap(RuntimeError):
    """Raised when Binance sequence continuity is broken."""


@dataclass(slots=True)
class LastTrade:
    price: float | None = None
    quantity: float = 0.0
    buyer_is_maker: bool | None = None
    exchange_ts_ms: int = 0


@dataclass(slots=True)
class LastLiquidation:
    side: str | None = None
    notional: float = 0.0
    exchange_ts_ms: int = 0


class LocalOrderBook:
    def __init__(self, symbol: str, max_levels: int = 1000) -> None:
        self.symbol = symbol.upper()
        self.max_levels = max_levels
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.last_update_id = 0
        self.started = False
        self.last_event_ts_ms = 0
        self.last_trade = LastTrade()
        self.last_liquidation = LastLiquidation()

    @staticmethod
    def _load_side(levels: Iterable[Iterable[Any]]) -> dict[float, float]:
        result: dict[float, float] = {}
        for level in levels:
            try:
                price, quantity = float(level[0]), float(level[1])
            except (IndexError, TypeError, ValueError):
                continue
            if price > 0 and quantity > 0:
                result[price] = quantity
        return result

    def set_snapshot(self, payload: dict[str, Any]) -> None:
        self.bids = self._load_side(payload.get("bids", []))
        self.asks = self._load_side(payload.get("asks", []))
        self.last_update_id = int(payload.get("lastUpdateId", 0))
        if self.last_update_id <= 0:
            raise ValueError("Snapshot does not contain a valid lastUpdateId")
        self.started = False
        self._trim()

    @staticmethod
    def _apply_levels(side: dict[float, float], updates: Iterable[Iterable[Any]]) -> None:
        for level in updates:
            try:
                price, quantity = float(level[0]), float(level[1])
            except (IndexError, TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if quantity <= 0:
                side.pop(price, None)
            else:
                side[price] = quantity

    def apply_diff(self, event: dict[str, Any]) -> bool:
        first_id = int(event.get("U", 0))
        final_id = int(event.get("u", 0))
        previous_final = int(event.get("pu", 0) or 0)
        if final_id <= self.last_update_id:
            return False
        if not self.last_update_id:
            raise OrderBookGap("Diff received before REST snapshot")

        if not self.started:
            expected = self.last_update_id + 1
            if not (first_id <= expected <= final_id or first_id <= self.last_update_id <= final_id):
                raise OrderBookGap(
                    f"First diff does not bridge snapshot: snapshot={self.last_update_id}, U={first_id}, u={final_id}"
                )
            self.started = True
        else:
            if previous_final and previous_final != self.last_update_id:
                raise OrderBookGap(
                    f"Futures pu mismatch: expected {self.last_update_id}, received {previous_final}"
                )
            if not previous_final and first_id > self.last_update_id + 1:
                raise OrderBookGap(
                    f"Sequence gap: expected <= {self.last_update_id + 1}, received U={first_id}"
                )

        self._apply_levels(self.bids, event.get("b", []))
        self._apply_levels(self.asks, event.get("a", []))
        self.last_update_id = final_id
        self.last_event_ts_ms = int(event.get("E", event.get("T", 0)) or 0)
        self._trim()
        return True

    def update_trade(self, event: dict[str, Any]) -> None:
        try:
            self.last_trade = LastTrade(
                price=float(event.get("p", 0.0)),
                quantity=float(event.get("q", 0.0)),
                buyer_is_maker=bool(event.get("m")),
                exchange_ts_ms=int(event.get("T", event.get("E", 0)) or 0),
            )
        except (TypeError, ValueError):
            return

    def update_liquidation(self, event: dict[str, Any]) -> None:
        order = event.get("o", event)
        try:
            price = float(order.get("ap") or order.get("p") or 0.0)
            quantity = float(order.get("q") or order.get("z") or 0.0)
            self.last_liquidation = LastLiquidation(
                side=str(order.get("S") or "").upper() or None,
                notional=abs(price * quantity),
                exchange_ts_ms=int(order.get("T", event.get("E", 0)) or 0),
            )
        except (TypeError, ValueError):
            return

    def _trim(self) -> None:
        if len(self.bids) > self.max_levels:
            keep = sorted(self.bids, reverse=True)[: self.max_levels]
            self.bids = {price: self.bids[price] for price in keep}
        if len(self.asks) > self.max_levels:
            keep = sorted(self.asks)[: self.max_levels]
            self.asks = {price: self.asks[price] for price in keep}

    def snapshot(self, levels: int = 20, local_ts_ms: int | None = None) -> BookSnapshot:
        levels = max(1, levels)
        bid_levels = [BookLevel(price, self.bids[price]) for price in sorted(self.bids, reverse=True)[:levels]]
        ask_levels = [BookLevel(price, self.asks[price]) for price in sorted(self.asks)[:levels]]
        return BookSnapshot(
            symbol=self.symbol,
            exchange_ts_ms=self.last_event_ts_ms or self.last_trade.exchange_ts_ms or int(time.time() * 1000),
            local_ts_ms=local_ts_ms or int(time.time() * 1000),
            sequence=self.last_update_id,
            bids=bid_levels,
            asks=ask_levels,
            last_trade_price=self.last_trade.price,
            last_trade_quantity=self.last_trade.quantity,
            buyer_is_maker=self.last_trade.buyer_is_maker,
            last_trade_ts_ms=self.last_trade.exchange_ts_ms,
            liquidation_side=self.last_liquidation.side,
            liquidation_notional=self.last_liquidation.notional,
            liquidation_ts_ms=self.last_liquidation.exchange_ts_ms,
        )
