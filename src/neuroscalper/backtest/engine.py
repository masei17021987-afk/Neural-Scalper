from __future__ import annotations

import copy
import gzip
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from ..config import AppConfig
from ..decision import DecisionEngine
from ..domain import BookLevel, BookSnapshot, ClosedTrade
from ..execution.paper import PaperBroker
from ..features.microstructure import MicrostructureFeatureEngine
from ..market.synthetic import SyntheticMarket
from ..models.manager import ModelManager
from ..models.router import HierarchicalRegimeRouter
from ..paths import DATA_DIR
from ..risk.manager import RiskManager
from .metrics import summarize_performance

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BacktestResult:
    source: str
    steps: int
    elapsed_seconds: float
    metrics: dict[str, float | int]
    equity_curve: list[tuple[int, float]]
    trades: list[dict]
    regime_counts: dict[str, int]
    rejection_counts: dict[str, int]
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _snapshot_from_row(row: dict) -> BookSnapshot:
    return BookSnapshot(
        symbol=str(row.get("symbol") or "BTCUSDT"),
        exchange_ts_ms=int(row.get("exchange_ts_ms") or row.get("local_ts_ms") or 0),
        local_ts_ms=int(row.get("local_ts_ms") or row.get("exchange_ts_ms") or 0),
        sequence=int(row.get("sequence") or 0),
        bids=[BookLevel(float(item["price"]), float(item["quantity"])) for item in row.get("bids", [])],
        asks=[BookLevel(float(item["price"]), float(item["quantity"])) for item in row.get("asks", [])],
        last_trade_price=float(row["last_trade_price"]) if row.get("last_trade_price") is not None else None,
        last_trade_quantity=float(row.get("last_trade_quantity") or 0.0),
        buyer_is_maker=row.get("buyer_is_maker"),
        last_trade_ts_ms=int(row.get("last_trade_ts_ms") or 0),
        liquidation_side=row.get("liquidation_side"),
        liquidation_notional=float(row.get("liquidation_notional") or 0.0),
        liquidation_ts_ms=int(row.get("liquidation_ts_ms") or 0),
    )


def iter_recorded_snapshots(root: Path, symbol: str) -> Iterable[BookSnapshot]:
    files = sorted((root / symbol.upper()).glob("book_*.jsonl.gz"))
    if not files:
        raise FileNotFoundError(f"Нет записей стакана для {symbol} в {root}")
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    snapshot = _snapshot_from_row(row)
                except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                    continue
                if snapshot.bids and snapshot.asks:
                    yield snapshot


def run_backtest(
    config: AppConfig,
    source: str = "synthetic",
    steps: int = 6000,
    seed: int = 42,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> BacktestResult:
    started = time.time()
    cfg = copy.deepcopy(config)
    cfg.execution.mode = "paper"
    engine = MicrostructureFeatureEngine(cfg.market.depth_levels, cfg.model.sequence_length)
    model = ModelManager(
        checkpoint=cfg.model.checkpoint,
        hidden_size=cfg.model.hidden_size,
        dropout=cfg.model.dropout,
        use_gpu=cfg.model.use_gpu,
    )
    router = HierarchicalRegimeRouter(DATA_DIR / "backtest_router_memory.json")
    decision = DecisionEngine(cfg)
    broker = PaperBroker(cfg.execution, cfg.risk, DATA_DIR / "backtest_state.json", restore=False)
    broker.reset()
    risk = RiskManager(cfg.risk, cfg.execution, cfg.model)

    if source == "recorded":
        snapshots = iter_recorded_snapshots(DATA_DIR / "records", cfg.market.symbol)
    else:
        market = SyntheticMarket(cfg.market.symbol, seed=seed, levels=cfg.market.depth_levels)
        snapshots = (market.step(cfg.market.update_ms) for _ in range(max(200, steps)))

    equity_curve: list[tuple[int, float]] = []
    signals = orders = fills = rejected = 0
    regime_counts: dict[str, int] = {}
    rejection_counts: dict[str, int] = {}
    last_decision_ts = 0
    processed = 0
    fill_count = 0

    for snapshot in snapshots:
        processed += 1
        if source == "recorded" and processed > steps:
            break
        frame = engine.update(snapshot)
        regime_counts[frame.regime] = regime_counts.get(frame.regime, 0) + 1
        closed = broker.on_snapshot(snapshot)
        if len(broker.fills) > fill_count:
            fills += len(broker.fills) - fill_count
            fill_count = len(broker.fills)
        for trade in closed:
            risk.record_closed_trade(trade.net_pnl, trade.closed_ts_ms)
            notional = max(trade.entry_price * trade.quantity, 1e-9)
            router.update(trade.regime, trade.net_pnl / notional * 10_000.0)
        risk.sync_equity(broker.balance, broker.equity)
        equity_curve.append((snapshot.local_ts_ms, broker.equity))

        # Decisions every 500 ms keep replay responsive and avoid treating every
        # depth message as an independent opportunity.
        if snapshot.local_ts_ms - last_decision_ts >= 500:
            last_decision_ts = snapshot.local_ts_ms
            prediction = model.predict(frame)
            route = router.route(frame.regime, cfg.strategies.model_weight, cfg.strategies.rules_weight)
            signal = decision.decide(frame, prediction, route)
            signals += 1
            risk_decision = risk.evaluate(
                signal, snapshot, broker.open_positions_count(), route.size_multiplier, check_staleness=False
            )
            if risk_decision.allowed and not broker.pending_orders and not broker.position:
                quantity = risk.position_size(snapshot.mid, route.size_multiplier)
                order = broker.submit_signal(signal, quantity, snapshot)
                if order:
                    orders += 1
            else:
                rejected += 1
                rejection_counts[risk_decision.code] = rejection_counts.get(risk_decision.code, 0) + 1

        if progress and processed % max(100, steps // 50) == 0:
            progress({
                "stage": "backtest",
                "progress": min(0.98, processed / max(steps, 1)),
                "message": f"Воспроизведено {processed:,} событий",
                "equity": broker.equity,
                "trades": len(broker.trades),
            })

    if broker.position:
        final_snapshot = snapshot  # type: ignore[possibly-undefined]
        trade = broker.close_position(final_snapshot, "END_OF_TEST")
        if trade:
            risk.record_closed_trade(trade.net_pnl, trade.closed_ts_ms)
            equity_curve.append((final_snapshot.local_ts_ms, broker.equity))

    metrics = summarize_performance(
        broker.trades,
        equity_curve,
        cfg.risk.initial_balance,
        signals,
        orders,
        fills,
        rejected,
    )
    notes = [
        "Комиссии, спред, проскальзывание, задержка и очередь лимитной заявки учтены.",
        "Результат синтетического теста проверяет механику, а не доказывает будущую доходность.",
        "Для принятия решения используйте записанные реальные данные и walk-forward разделение.",
    ]
    result = BacktestResult(
        source=source,
        steps=processed,
        elapsed_seconds=round(time.time() - started, 3),
        metrics=metrics,
        equity_curve=equity_curve[:: max(1, len(equity_curve) // 800)],
        trades=[trade.to_dict() for trade in broker.trades[-500:]],
        regime_counts=regime_counts,
        rejection_counts=rejection_counts,
        notes=notes,
    )
    report_path = DATA_DIR.parent / "reports" / "latest_backtest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if progress:
        progress({"stage": "complete", "progress": 1.0, "message": "Бэктест завершён", **result.to_dict()})
    logger.info("Backtest complete: %s", metrics)
    return result
