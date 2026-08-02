from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from ..domain import BookLevel, BookSnapshot


@dataclass(slots=True)
class SyntheticRegime:
    name: str
    drift_bps: float
    volatility_bps: float
    spread_bps: float
    depth_scale: float


REGIMES = (
    SyntheticRegime("TREND_UP", 0.16, 0.85, 0.8, 1.0),
    SyntheticRegime("TREND_DOWN", -0.16, 0.85, 0.8, 1.0),
    SyntheticRegime("RANGE", 0.0, 0.55, 0.7, 1.25),
    SyntheticRegime("BREAKOUT", 0.32, 1.9, 1.6, 0.65),
    SyntheticRegime("HIGH_VOL", 0.0, 2.8, 2.3, 0.55),
)


class SyntheticMarket:
    """Deterministic L2 market used for first-run demo and tests."""

    def __init__(self, symbol: str = "BTCUSDT", seed: int = 42, levels: int = 20) -> None:
        self.symbol = symbol.upper()
        self.random = random.Random(seed)
        self.levels = levels
        self.price = 60_000.0
        self.sequence = 1
        self.tick = 0
        self.regime = REGIMES[2]
        self.regime_until = 0
        self.mean_anchor = self.price
        self.last_ts_ms = int(time.time() * 1000)

    def _switch_regime(self) -> None:
        self.regime = self.random.choices(REGIMES, weights=[2.2, 2.2, 3.0, 1.0, 0.8], k=1)[0]
        self.regime_until = self.tick + self.random.randint(250, 900)
        self.mean_anchor = self.price

    def step(self, dt_ms: int = 100) -> BookSnapshot:
        if self.tick >= self.regime_until:
            self._switch_regime()
        self.tick += 1
        self.sequence += 1
        self.last_ts_ms += dt_ms

        mean_reversion = 0.0
        if self.regime.name == "RANGE":
            mean_reversion = (self.mean_anchor - self.price) / max(self.price, 1.0) * 10_000.0 * 0.025
        impulse = self.regime.drift_bps + mean_reversion + self.random.gauss(0.0, self.regime.volatility_bps)
        if self.regime.name == "BREAKOUT" and self.random.random() < 0.04:
            impulse += self.random.choice((-1, 1)) * self.random.uniform(5.0, 16.0)
        self.price *= math.exp(impulse / 10_000.0)

        imbalance = max(-0.92, min(0.92, math.tanh((impulse + self.random.gauss(0, 1.2)) / 2.5)))
        spread_bps = max(0.25, self.regime.spread_bps * self.random.uniform(0.75, 1.35))
        half_spread = self.price * spread_bps / 20_000.0
        best_bid = self.price - half_spread
        best_ask = self.price + half_spread
        tick_size = max(0.01, round(self.price * 0.000001, 2))

        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        base_depth = 1.8 * self.regime.depth_scale
        for i in range(self.levels):
            distance = (i + 1) * tick_size * (1.0 + i * 0.035)
            bid_qty = base_depth * (1.0 + imbalance) * self.random.lognormvariate(0.0, 0.35) * (1.0 + i * 0.05)
            ask_qty = base_depth * (1.0 - imbalance) * self.random.lognormvariate(0.0, 0.35) * (1.0 + i * 0.05)
            bids.append(BookLevel(max(tick_size, best_bid - distance), max(0.001, bid_qty)))
            asks.append(BookLevel(best_ask + distance, max(0.001, ask_qty)))

        aggressive_buy = self.random.random() < (0.5 + imbalance * 0.34)
        trade_price = best_ask if aggressive_buy else best_bid
        trade_qty = max(0.001, self.random.lognormvariate(-0.2, 0.8))
        liquidation_side = None
        liquidation_notional = 0.0
        if abs(impulse) > 5.5 and self.random.random() < 0.18:
            liquidation_side = "SELL" if impulse < 0 else "BUY"
            liquidation_notional = self.random.uniform(25_000.0, 750_000.0) * min(3.0, abs(impulse) / 5.5)

        return BookSnapshot(
            symbol=self.symbol,
            exchange_ts_ms=self.last_ts_ms,
            local_ts_ms=self.last_ts_ms + self.random.randint(4, 35),
            sequence=self.sequence,
            bids=bids,
            asks=asks,
            last_trade_price=trade_price,
            last_trade_quantity=trade_qty,
            buyer_is_maker=not aggressive_buy,
            last_trade_ts_ms=self.last_ts_ms,
            liquidation_side=liquidation_side,
            liquidation_notional=liquidation_notional,
            liquidation_ts_ms=self.last_ts_ms if liquidation_notional > 0 else 0,
        )
