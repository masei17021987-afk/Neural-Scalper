from __future__ import annotations

import math
from collections import deque
from statistics import fmean
from typing import Iterable

import numpy as np

from ..domain import BookSnapshot, FeatureFrame


FEATURE_NAMES = [
    "mid_price",
    "spread_bps",
    "microprice_delta_bps",
    "obi_1",
    "obi_5",
    "obi_10",
    "obi_20",
    "bid_depth_5",
    "ask_depth_5",
    "bid_depth_20",
    "ask_depth_20",
    "top_size_ratio",
    "bid_gap_bps",
    "ask_gap_bps",
    "depth_slope_bid",
    "depth_slope_ask",
    "return_1_bps",
    "return_3_bps",
    "return_10_bps",
    "return_30_bps",
    "return_60_bps",
    "realized_vol_10_bps",
    "realized_vol_30_bps",
    "trade_imbalance_5",
    "trade_imbalance_20",
    "trade_imbalance_50",
    "trade_intensity_20",
    "volume_acceleration",
    "price_impact_bps",
    "latency_ms",
    "liquidation_buy_pressure",
    "liquidation_sell_pressure",
    "liquidity_score",
    "momentum_quality",
    "mean_reversion_pressure",
    "event_rate_hz",
]


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if abs(denominator) > 1e-12 else 0.0


def _imbalance(bids: Iterable[float], asks: Iterable[float]) -> float:
    bid = float(sum(bids))
    ask = float(sum(asks))
    return _safe_div(bid - ask, bid + ask)


def _return_bps(prices: deque[float], lag: int) -> float:
    if len(prices) <= lag:
        return 0.0
    old = prices[-lag - 1]
    current = prices[-1]
    return ((current / old) - 1.0) * 10_000.0 if old else 0.0


def _realized_vol(prices: deque[float], window: int) -> float:
    if len(prices) < 3:
        return 0.0
    values = list(prices)[-min(len(prices), window + 1):]
    returns = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous) * 10_000.0)
    if len(returns) < 2:
        return abs(returns[0]) if returns else 0.0
    return float(np.std(np.asarray(returns, dtype=np.float64), ddof=0))


class MicrostructureFeatureEngine:
    def __init__(self, levels: int = 20, sequence_length: int = 64) -> None:
        self.levels = max(5, levels)
        self.sequence_length = max(16, sequence_length)
        self.mid_prices: deque[float] = deque(maxlen=600)
        self.timestamps: deque[int] = deque(maxlen=600)
        self.signed_trades: deque[float] = deque(maxlen=500)
        self.trade_notionals: deque[float] = deque(maxlen=500)
        self.lob_history: deque[list[list[float]]] = deque(maxlen=self.sequence_length)
        self.last_trade_ts = -1
        self.last_liquidation_ts = -1
        self.liquidations: deque[tuple[int, float, float]] = deque(maxlen=500)
        self.last_frame: FeatureFrame | None = None

    @property
    def ready(self) -> bool:
        return len(self.lob_history) >= self.sequence_length

    def _side_quantities(self, snapshot: BookSnapshot, count: int) -> tuple[list[float], list[float]]:
        bids = [level.quantity for level in snapshot.bids[:count]]
        asks = [level.quantity for level in snapshot.asks[:count]]
        while len(bids) < count:
            bids.append(0.0)
        while len(asks) < count:
            asks.append(0.0)
        return bids, asks

    def _lob_row(self, snapshot: BookSnapshot) -> list[list[float]]:
        mid = max(snapshot.mid, 1e-12)
        rows: list[list[float]] = []
        for index in range(self.levels):
            bid = snapshot.bids[index] if index < len(snapshot.bids) else None
            ask = snapshot.asks[index] if index < len(snapshot.asks) else None
            bid_price = (((bid.price / mid) - 1.0) * 10_000.0) if bid else 0.0
            ask_price = (((ask.price / mid) - 1.0) * 10_000.0) if ask else 0.0
            bid_qty = math.log1p(max(0.0, bid.quantity)) if bid else 0.0
            ask_qty = math.log1p(max(0.0, ask.quantity)) if ask else 0.0
            rows.append([bid_price, bid_qty, ask_price, ask_qty])
        return rows

    def _trade_features(self, snapshot: BookSnapshot) -> None:
        trade_ts = snapshot.last_trade_ts_ms
        if snapshot.last_trade_price and snapshot.last_trade_quantity > 0 and trade_ts > 0 and trade_ts != self.last_trade_ts:
            sign = -1.0 if snapshot.buyer_is_maker else 1.0
            self.signed_trades.append(sign * snapshot.last_trade_quantity)
            self.trade_notionals.append(snapshot.last_trade_price * snapshot.last_trade_quantity)
            self.last_trade_ts = trade_ts

        liquidation_ts = snapshot.liquidation_ts_ms
        if snapshot.liquidation_notional > 0 and liquidation_ts > 0 and liquidation_ts != self.last_liquidation_ts:
            buy = snapshot.liquidation_notional if snapshot.liquidation_side == "BUY" else 0.0
            sell = snapshot.liquidation_notional if snapshot.liquidation_side == "SELL" else 0.0
            self.liquidations.append((snapshot.local_ts_ms, buy, sell))
            self.last_liquidation_ts = liquidation_ts

    def _trade_imbalance(self, window: int) -> float:
        values = list(self.signed_trades)[-window:]
        total = sum(abs(value) for value in values)
        return _safe_div(sum(values), total)

    def _liquidation_pressure(self, now_ms: int, horizon_ms: int = 10_000) -> tuple[float, float]:
        while self.liquidations and now_ms - self.liquidations[0][0] > horizon_ms:
            self.liquidations.popleft()
        buy = sum(item[1] for item in self.liquidations)
        sell = sum(item[2] for item in self.liquidations)
        scale = max(1.0, buy + sell)
        return buy / scale, sell / scale

    def _classify_regime(self, features: dict[str, float]) -> str:
        spread = features["spread_bps"]
        depth = features["bid_depth_20"] + features["ask_depth_20"]
        vol = features["realized_vol_30_bps"]
        ret10 = features["return_10_bps"]
        ret30 = features["return_30_bps"]
        imbalance = features["obi_10"]
        if spread > 5.0 or depth < 2.0:
            return "LOW_LIQUIDITY"
        if vol > 3.0:
            return "HIGH_VOL"
        if abs(ret10) > 6.0 and vol > 1.1:
            return "BREAKOUT_UP" if ret10 > 0 else "BREAKOUT_DOWN"
        if abs(ret30) > 7.0 and abs(imbalance) > 0.12:
            return "TREND_UP" if ret30 > 0 else "TREND_DOWN"
        return "RANGE"

    def update(self, snapshot: BookSnapshot) -> FeatureFrame:
        mid = snapshot.mid
        if mid <= 0 or not snapshot.bids or not snapshot.asks:
            raise ValueError("A valid two-sided order book is required")
        self.mid_prices.append(mid)
        self.timestamps.append(snapshot.local_ts_ms)
        self._trade_features(snapshot)
        self.lob_history.append(self._lob_row(snapshot))

        bid1, ask1 = self._side_quantities(snapshot, 1)
        bid5, ask5 = self._side_quantities(snapshot, 5)
        bid10, ask10 = self._side_quantities(snapshot, 10)
        bid20, ask20 = self._side_quantities(snapshot, min(20, self.levels))
        best_bid_qty, best_ask_qty = bid1[0], ask1[0]
        microprice = _safe_div(
            snapshot.best_ask * best_bid_qty + snapshot.best_bid * best_ask_qty,
            best_bid_qty + best_ask_qty,
        )
        micro_delta = ((microprice / mid) - 1.0) * 10_000.0 if microprice else 0.0
        bid_gap = (
            (snapshot.bids[0].price - snapshot.bids[1].price) / mid * 10_000.0
            if len(snapshot.bids) > 1 else 0.0
        )
        ask_gap = (
            (snapshot.asks[1].price - snapshot.asks[0].price) / mid * 10_000.0
            if len(snapshot.asks) > 1 else 0.0
        )
        bid_slope = _safe_div(sum((index + 1) * qty for index, qty in enumerate(bid20)), sum(bid20))
        ask_slope = _safe_div(sum((index + 1) * qty for index, qty in enumerate(ask20)), sum(ask20))
        vol10 = _realized_vol(self.mid_prices, 10)
        vol30 = _realized_vol(self.mid_prices, 30)
        ret1 = _return_bps(self.mid_prices, 1)
        ret3 = _return_bps(self.mid_prices, 3)
        ret10 = _return_bps(self.mid_prices, 10)
        ret30 = _return_bps(self.mid_prices, 30)
        ret60 = _return_bps(self.mid_prices, 60)
        imbalance5 = self._trade_imbalance(5)
        imbalance20 = self._trade_imbalance(20)
        imbalance50 = self._trade_imbalance(50)
        notionals20 = list(self.trade_notionals)[-20:]
        notionals_prev = list(self.trade_notionals)[-40:-20]
        intensity = fmean(notionals20) if notionals20 else 0.0
        prev_intensity = fmean(notionals_prev) if notionals_prev else intensity
        volume_acceleration = _safe_div(intensity - prev_intensity, max(prev_intensity, 1.0))
        price_impact = _safe_div(ret3, max(1.0, sum(notionals20[-3:]))) * 100_000.0
        latency_ms = max(0.0, float(snapshot.local_ts_ms - snapshot.exchange_ts_ms))
        liq_buy, liq_sell = self._liquidation_pressure(snapshot.local_ts_ms)
        depth_total = sum(bid20) + sum(ask20)
        liquidity_score = max(0.0, min(1.0, math.tanh(depth_total / 50.0) * math.exp(-snapshot.spread_bps / 6.0)))
        momentum_quality = math.tanh((ret10 * (0.45 + abs(imbalance20))) / max(1.0, vol30 * 3.0))
        mean_reversion = -math.tanh(ret10 / max(2.0, vol30 * 4.0)) if abs(ret30) < 8.0 else 0.0
        if len(self.timestamps) > 2:
            elapsed = max(1, self.timestamps[-1] - self.timestamps[0]) / 1000.0
            event_rate = (len(self.timestamps) - 1) / elapsed
        else:
            event_rate = 0.0

        values_map = {
            "mid_price": mid,
            "spread_bps": snapshot.spread_bps,
            "microprice_delta_bps": micro_delta,
            "obi_1": _imbalance(bid1, ask1),
            "obi_5": _imbalance(bid5, ask5),
            "obi_10": _imbalance(bid10, ask10),
            "obi_20": _imbalance(bid20, ask20),
            "bid_depth_5": sum(bid5),
            "ask_depth_5": sum(ask5),
            "bid_depth_20": sum(bid20),
            "ask_depth_20": sum(ask20),
            "top_size_ratio": math.log((best_bid_qty + 1e-9) / (best_ask_qty + 1e-9)),
            "bid_gap_bps": bid_gap,
            "ask_gap_bps": ask_gap,
            "depth_slope_bid": bid_slope,
            "depth_slope_ask": ask_slope,
            "return_1_bps": ret1,
            "return_3_bps": ret3,
            "return_10_bps": ret10,
            "return_30_bps": ret30,
            "return_60_bps": ret60,
            "realized_vol_10_bps": vol10,
            "realized_vol_30_bps": vol30,
            "trade_imbalance_5": imbalance5,
            "trade_imbalance_20": imbalance20,
            "trade_imbalance_50": imbalance50,
            "trade_intensity_20": math.log1p(max(0.0, intensity)),
            "volume_acceleration": max(-5.0, min(5.0, volume_acceleration)),
            "price_impact_bps": max(-50.0, min(50.0, price_impact)),
            "latency_ms": latency_ms,
            "liquidation_buy_pressure": liq_buy,
            "liquidation_sell_pressure": liq_sell,
            "liquidity_score": liquidity_score,
            "momentum_quality": momentum_quality,
            "mean_reversion_pressure": mean_reversion,
            "event_rate_hz": event_rate,
        }
        regime = self._classify_regime(values_map)
        lob = list(self.lob_history)
        if lob:
            while len(lob) < self.sequence_length:
                lob.insert(0, lob[0])
        frame = FeatureFrame(
            symbol=snapshot.symbol,
            exchange_ts_ms=snapshot.exchange_ts_ms,
            local_ts_ms=snapshot.local_ts_ms,
            names=list(FEATURE_NAMES),
            values=[float(values_map[name]) for name in FEATURE_NAMES],
            lob_tensor=lob[-self.sequence_length:],
            regime=regime,
            metadata={
                "ready": self.ready,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "sequence": snapshot.sequence,
            },
        )
        self.last_frame = frame
        return frame
