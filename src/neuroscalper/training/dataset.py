from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from ..config import AppConfig
from ..domain import BookLevel, BookSnapshot
from ..features import MicrostructureFeatureEngine
from ..market.synthetic import SyntheticMarket


@dataclass(slots=True)
class DatasetBundle:
    x: np.ndarray
    y: np.ndarray
    edge: np.ndarray
    volatility: np.ndarray
    timestamps: np.ndarray
    metadata: dict[str, object]


def _label_executable_returns(
    mids: list[float],
    best_bids: list[float],
    best_asks: list[float],
    horizon: int,
    threshold_bps: float,
    round_trip_fee_bps: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create labels from prices that could actually be crossed.

    LONG enters at the current ask and exits at the future bid. SHORT enters at
    the current bid and exits at the future ask. Fees are then subtracted. This
    is deliberately more conservative than labeling a mid-price movement.
    """
    length = len(mids) - horizon
    labels = np.ones(length, dtype=np.int64)
    edges = np.zeros(length, dtype=np.float32)
    volatility = np.zeros(length, dtype=np.float32)
    mid_values = np.asarray(mids, dtype=np.float64)
    bids = np.asarray(best_bids, dtype=np.float64)
    asks = np.asarray(best_asks, dtype=np.float64)
    for index in range(length):
        future_index = index + horizon
        long_net = ((bids[future_index] / asks[index]) - 1.0) * 10_000.0 - round_trip_fee_bps
        short_net = ((bids[index] / asks[future_index]) - 1.0) * 10_000.0 - round_trip_fee_bps
        if long_net > threshold_bps and long_net >= short_net:
            labels[index] = 2
            edges[index] = long_net
        elif short_net > threshold_bps:
            labels[index] = 0
            edges[index] = -short_net
        else:
            # Preserve a weak signed target for the auxiliary edge head while
            # keeping the classification target FLAT.
            edges[index] = long_net if abs(long_net) >= abs(short_net) else -short_net
        window = mid_values[index : future_index + 1]
        returns = np.diff(np.log(np.maximum(window, 1e-12))) * 10_000.0
        volatility[index] = float(np.std(returns)) if returns.size else 0.0
    return labels, edges, volatility


def build_synthetic_dataset(config: AppConfig, samples: int = 6000, seed: int = 42) -> DatasetBundle:
    horizon = 12
    warmup = config.model.sequence_length + horizon + 20
    market = SyntheticMarket(config.market.symbol, seed=seed, levels=config.market.depth_levels)
    engine = MicrostructureFeatureEngine(config.market.depth_levels, config.model.sequence_length)
    tensors: list[np.ndarray] = []
    prices: list[float] = []
    best_bids: list[float] = []
    best_asks: list[float] = []
    timestamps: list[int] = []
    for _ in range(samples + warmup):
        snapshot = market.step(config.market.update_ms)
        frame = engine.update(snapshot)
        if engine.ready:
            tensors.append(np.asarray(frame.lob_tensor, dtype=np.float32))
            prices.append(snapshot.mid)
            best_bids.append(snapshot.best_bid)
            best_asks.append(snapshot.best_ask)
            timestamps.append(snapshot.local_ts_ms)
    labels, edges, volatility = _label_executable_returns(
        prices, best_bids, best_asks, horizon,
        threshold_bps=max(0.5, config.model.min_net_edge_bps),
        round_trip_fee_bps=config.execution.maker_fee_bps + config.execution.taker_fee_bps + config.execution.slippage_bps,
    )
    usable = len(labels)
    return DatasetBundle(
        x=np.asarray(tensors[:usable], dtype=np.float32),
        y=labels,
        edge=edges,
        volatility=volatility,
        timestamps=np.asarray(timestamps[:usable], dtype=np.int64),
        metadata={"source": "synthetic", "samples": usable, "horizon_ticks": horizon, "seed": seed, "labels": "executable_bid_ask_after_fees"},
    )


def _snapshot_from_payload(payload: dict) -> BookSnapshot:
    return BookSnapshot(
        symbol=str(payload["symbol"]),
        exchange_ts_ms=int(payload["exchange_ts_ms"]),
        local_ts_ms=int(payload["local_ts_ms"]),
        sequence=int(payload.get("sequence", 0)),
        bids=[BookLevel(float(row["price"]), float(row["quantity"])) for row in payload.get("bids", [])],
        asks=[BookLevel(float(row["price"]), float(row["quantity"])) for row in payload.get("asks", [])],
        last_trade_price=float(payload["last_trade_price"]) if payload.get("last_trade_price") else None,
        last_trade_quantity=float(payload.get("last_trade_quantity", 0.0)),
        buyer_is_maker=payload.get("buyer_is_maker"),
        last_trade_ts_ms=int(payload.get("last_trade_ts_ms", 0)),
        liquidation_side=payload.get("liquidation_side"),
        liquidation_notional=float(payload.get("liquidation_notional", 0.0)),
        liquidation_ts_ms=int(payload.get("liquidation_ts_ms", 0)),
    )


def iter_recorded_snapshots(paths: Iterable[Path]) -> Iterable[BookSnapshot]:
    for path in sorted(paths):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                    yield _snapshot_from_payload(payload)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue


def build_recorded_dataset(config: AppConfig, record_root: Path) -> DatasetBundle:
    paths = list(record_root.rglob("book_*.jsonl.gz")) + list(record_root.rglob("book_*.jsonl"))
    if not paths:
        raise FileNotFoundError(f"No recorded book files found in {record_root}")
    horizon = 12
    engine = MicrostructureFeatureEngine(config.market.depth_levels, config.model.sequence_length)
    tensors: list[np.ndarray] = []
    prices: list[float] = []
    best_bids: list[float] = []
    best_asks: list[float] = []
    timestamps: list[int] = []
    for snapshot in iter_recorded_snapshots(paths):
        if snapshot.symbol != config.market.symbol:
            continue
        frame = engine.update(snapshot)
        if engine.ready:
            tensors.append(np.asarray(frame.lob_tensor, dtype=np.float32))
            prices.append(snapshot.mid)
            best_bids.append(snapshot.best_bid)
            best_asks.append(snapshot.best_ask)
            timestamps.append(snapshot.local_ts_ms)
    if len(tensors) <= horizon + 100:
        raise ValueError("Too few valid snapshots for training")
    labels, edges, volatility = _label_executable_returns(
        prices, best_bids, best_asks, horizon,
        threshold_bps=max(0.5, config.model.min_net_edge_bps),
        round_trip_fee_bps=config.execution.maker_fee_bps + config.execution.taker_fee_bps + config.execution.slippage_bps,
    )
    usable = len(labels)
    return DatasetBundle(
        x=np.asarray(tensors[:usable], dtype=np.float32),
        y=labels,
        edge=edges,
        volatility=volatility,
        timestamps=np.asarray(timestamps[:usable], dtype=np.int64),
        metadata={"source": "recorded", "samples": usable, "horizon_ticks": horizon, "files": len(paths), "labels": "executable_bid_ask_after_fees"},
    )
