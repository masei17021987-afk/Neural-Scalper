from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    POST_ONLY = "POST_ONLY"


@dataclass(slots=True)
class BookLevel:
    price: float
    quantity: float


@dataclass(slots=True)
class BookSnapshot:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    sequence: int
    bids: list[BookLevel]
    asks: list[BookLevel]
    last_trade_price: float | None = None
    last_trade_quantity: float = 0.0
    buyer_is_maker: bool | None = None
    last_trade_ts_ms: int = 0
    liquidation_side: str | None = None
    liquidation_notional: float = 0.0
    liquidation_ts_ms: int = 0

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def mid(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return self.best_bid or self.best_ask or self.last_trade_price or 0.0

    @property
    def spread_bps(self) -> float:
        mid = self.mid
        return ((self.best_ask - self.best_bid) / mid * 10_000.0) if mid else 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mid"] = self.mid
        payload["spread_bps"] = self.spread_bps
        return payload


@dataclass(slots=True)
class FeatureFrame:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    names: list[str]
    values: list[float]
    lob_tensor: list[list[list[float]]]
    regime: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_map(self) -> dict[str, float]:
        return dict(zip(self.names, self.values, strict=False))


@dataclass(slots=True)
class ModelPrediction:
    probabilities: dict[str, float]
    expected_edge_bps: float
    expected_volatility_bps: float
    model_name: str
    model_ready: bool


@dataclass(slots=True)
class StrategyVote:
    strategy_id: str
    score: float
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TradingSignal:
    id: str
    symbol: str
    ts_ms: int
    direction: Direction
    confidence: float
    expected_gross_edge_bps: float
    expected_net_edge_bps: float
    order_type: OrderType
    reasons: list[str]
    warnings: list[str]
    regime: str
    model: dict[str, Any]
    votes: list[dict[str, Any]]
    status: str = "CREATED"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        payload["order_type"] = self.order_type.value
        return payload


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Order:
    id: str
    signal_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float
    price: float | None
    created_ts_ms: int
    active_ts_ms: int
    cancel_ts_ms: int | None
    queue_ahead: float = 0.0
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    status: Literal["PENDING", "OPEN", "PARTIAL", "FILLED", "CANCELLED", "REJECTED"] = "PENDING"


@dataclass(slots=True)
class Fill:
    id: str
    order_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    fee: float
    ts_ms: int
    liquidity: Literal["MAKER", "TAKER"]


@dataclass(slots=True)
class Position:
    symbol: str
    direction: Direction
    quantity: float
    entry_price: float
    opened_ts_ms: int
    stop_price: float
    take_profit_price: float
    trailing_anchor: float
    realized_pnl: float = 0.0
    fees: float = 0.0
    signal_id: str = ""


@dataclass(slots=True)
class ClosedTrade:
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    quantity: float
    entry_price: float
    exit_price: float
    opened_ts_ms: int
    closed_ts_ms: int
    gross_pnl: float
    fees: float
    net_pnl: float
    return_pct: float
    reason: str
    regime: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        return payload
