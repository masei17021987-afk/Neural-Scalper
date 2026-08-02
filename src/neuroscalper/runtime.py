from __future__ import annotations

import asyncio
import copy
import logging
import platform
import time
from collections import Counter, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from .backtest.engine import run_backtest
from .config import AppConfig, config_to_dict, load_config, save_config, update_config
from .decision import DecisionEngine
from .domain import BookSnapshot, Direction, RiskDecision, TradingSignal
from .execution.paper import PaperBroker
from .features.microstructure import MicrostructureFeatureEngine
from .logging_setup import memory_handler
from .market.binance import BinanceFuturesPublicCollector
from .market.recorder import EventRecorder
from .market.quality import DataQualityMonitor
from .market.synthetic import SyntheticMarket
from .models.manager import ModelManager
from .models.router import HierarchicalRegimeRouter, RouterDecision
from .paths import DATA_DIR, MODEL_DIR, REPORT_DIR, ensure_runtime_dirs
from .risk.manager import RiskManager
from .storage import Storage
from .strategies.ensemble import StrategyEnsemble
from .training.trainer import train_model

logger = logging.getLogger(__name__)


class NeuralScalperRuntime:
    """Single-process supervisor for data, inference, paper execution and jobs."""

    def __init__(self, config: AppConfig | None = None) -> None:
        ensure_runtime_dirs()
        self.config = config or load_config()
        self.storage = Storage()
        self.recorder = EventRecorder()
        self.router = HierarchicalRegimeRouter()
        self.mode = "stopped"
        self.source_label = "Остановлено"
        self.running = False
        self.started_ts_ms = 0
        self.last_error = ""
        self.collector_status: dict[str, Any] = {"state": "STOPPED"}
        self._task: asyncio.Task | None = None
        self._collector: BinanceFuturesPublicCollector | None = None
        self._stop_event = asyncio.Event()
        self._operation_lock = asyncio.Lock()
        self._last_decision_ts_ms = 0
        self._last_metric_ts_ms = 0
        self._snapshot_count = 0
        self._signal_count = 0
        self._ordered_count = 0
        self._rejection_counts: Counter[str] = Counter()
        self._recent_signals: deque[dict[str, Any]] = deque(maxlen=100)
        self._equity_curve: deque[tuple[int, float]] = deque(maxlen=1800)
        self._price_curve: deque[tuple[int, float]] = deque(maxlen=1800)
        self.last_snapshot: BookSnapshot | None = None
        self.last_frame = None
        self.last_prediction = None
        self.last_signal: TradingSignal | None = None
        self.last_risk_decision: RiskDecision | None = None
        self.last_route: RouterDecision | None = None
        self.data_quality = DataQualityMonitor(self.config.market.stale_after_ms)
        self.training_state: dict[str, Any] = {
            "running": False, "stage": "idle", "progress": 0.0, "message": "Обучение не запущено"
        }
        self.backtest_state: dict[str, Any] = {
            "running": False, "stage": "idle", "progress": 0.0, "message": "Бэктест не запущен"
        }
        self._training_task: asyncio.Task | None = None
        self._backtest_task: asyncio.Task | None = None
        self._build_components(restore=True)

    def _build_components(self, restore: bool) -> None:
        cfg = self.config
        self.features = MicrostructureFeatureEngine(cfg.market.depth_levels, cfg.model.sequence_length)
        try:
            self.model = ModelManager(
                checkpoint=cfg.model.checkpoint,
                hidden_size=cfg.model.hidden_size,
                dropout=cfg.model.dropout,
                use_gpu=cfg.model.use_gpu,
            )
        except Exception as exc:
            logger.exception("Model load failed; heuristic fallback enabled")
            self.last_error = f"Не удалось загрузить модель: {exc}"
            self.model = ModelManager(
                checkpoint="",
                hidden_size=cfg.model.hidden_size,
                dropout=cfg.model.dropout,
                use_gpu=cfg.model.use_gpu,
                autoload_default=False,
            )
        self.decision_engine = DecisionEngine(cfg)
        self.broker = PaperBroker(cfg.execution, cfg.risk, restore=restore)
        self.risk = RiskManager(cfg.risk, cfg.execution, cfg.model)
        self.risk.state.peak_equity = max(self.risk.state.peak_equity, self.broker.peak_balance)
        self.risk.sync_equity(self.broker.balance, self.broker.equity)

    async def close(self) -> None:
        await self.stop()
        for task in (self._training_task, self._backtest_task):
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.recorder.close()
        self.storage.close()

    def apply_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        old_market = (self.config.market.symbol, self.config.market.depth_levels, self.config.model.sequence_length)
        self.config = update_config(self.config, patch)
        save_config(self.config)
        self.decision_engine.update_config(self.config)
        self.risk.config = self.config.risk
        self.risk.execution = self.config.execution
        self.risk.model = self.config.model
        # Execution/risk limits are safe to apply immediately to the paper path.
        # The account itself is intentionally not reset when settings change.
        self.broker.execution = self.config.execution
        self.broker.risk = self.config.risk
        self.broker.fill_model.config = self.config.execution
        restart_required = old_market != (
            self.config.market.symbol, self.config.market.depth_levels, self.config.model.sequence_length
        )
        return {"config": config_to_dict(self.config), "restart_required": restart_required and self.running}

    async def _start(self, mode: str) -> dict[str, Any]:
        async with self._operation_lock:
            await self._stop_locked()
            self._stop_event = asyncio.Event()
            self.mode = mode
            self.source_label = "Демо-рынок" if mode == "demo" else "Binance Futures: публичные данные"
            self.running = True
            self.started_ts_ms = int(time.time() * 1000)
            self.last_error = ""
            self.collector_status = {"state": "STARTING", "mode": mode}
            self.features = MicrostructureFeatureEngine(
                self.config.market.depth_levels, self.config.model.sequence_length
            )
            self.data_quality = DataQualityMonitor(self.config.market.stale_after_ms)
            if mode == "demo":
                self._task = asyncio.create_task(self._run_demo(), name="neuroscalper-demo")
            else:
                self._task = asyncio.create_task(self._run_binance(), name="neuroscalper-binance")
            logger.info("Runtime started in %s mode", mode)
            return {"ok": True, "mode": mode}

    async def start_demo(self) -> dict[str, Any]:
        return await self._start("demo")

    async def start_public_market(self) -> dict[str, Any]:
        return await self._start("public_market")

    async def stop(self) -> dict[str, Any]:
        async with self._operation_lock:
            return await self._stop_locked()

    async def _stop_locked(self) -> dict[str, Any]:
        was_running = self.running or bool(self._task and not self._task.done())
        self._stop_event.set()
        if self._collector:
            self._collector.stop()
        task = self._task
        self._task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._collector = None
        self.running = False
        self.mode = "stopped"
        self.source_label = "Остановлено"
        self.collector_status = {"state": "STOPPED"}
        if was_running:
            logger.info("Runtime stopped")
        return {"ok": True, "stopped": was_running}

    async def _run_demo(self) -> None:
        market = SyntheticMarket(
            self.config.market.symbol, seed=42, levels=self.config.market.depth_levels
        )
        self.collector_status = {"state": "CONNECTED", "kind": "SYNTHETIC", "messages": 0}
        try:
            while not self._stop_event.is_set():
                snapshot = market.step(self.config.market.update_ms)
                self.collector_status["messages"] = int(self.collector_status.get("messages", 0)) + 1
                self.collector_status["regime"] = market.regime.name
                await self._handle_snapshot(snapshot, record=False)
                await asyncio.sleep(self.config.market.update_ms / 1000.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            self.collector_status = {"state": "ERROR", "error": str(exc)}
            logger.exception("Demo runtime failed")
        finally:
            if self.mode == "demo":
                self.running = False

    def _collector_status_callback(self, payload: dict[str, Any]) -> None:
        self.collector_status = payload

    async def _run_binance(self) -> None:
        self._collector = BinanceFuturesPublicCollector(
            self.config.market.symbol,
            self.config.market.depth_levels,
            self.config.market.update_ms,
            self._collector_status_callback,
        )
        try:
            async for snapshot in self._collector.stream():
                if self._stop_event.is_set():
                    break
                await self._handle_snapshot(snapshot, record=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            self.collector_status = {"state": "ERROR", "error": str(exc)}
            logger.exception("Binance runtime failed")
        finally:
            if self.mode == "public_market":
                self.running = False

    async def _handle_snapshot(self, snapshot: BookSnapshot, record: bool) -> None:
        self._snapshot_count += 1
        self.last_snapshot = snapshot
        quality = self.data_quality.update(snapshot)
        self._price_curve.append((snapshot.local_ts_ms, snapshot.mid))
        if record and self.config.market.record_raw_events:
            self.recorder.write_snapshot(snapshot)
        try:
            frame = self.features.update(snapshot)
        except ValueError as exc:
            self.last_error = str(exc)
            return
        self.last_frame = frame
        if record and self.config.market.record_features:
            self.recorder.write_feature(frame)

        previous_fill_count = len(self.broker.fills)
        closed = self.broker.on_snapshot(snapshot)
        fill_delta = len(self.broker.fills) - previous_fill_count
        if fill_delta > 0:
            logger.info("Paper fills: +%s", fill_delta)
        for trade in closed:
            self.risk.record_closed_trade(trade.net_pnl, trade.closed_ts_ms)
            notional = max(trade.entry_price * trade.quantity, 1e-9)
            self.router.update(trade.regime, trade.net_pnl / notional * 10_000.0)
            self.storage.save_trade(trade.to_dict())
            self.storage.save_decision(trade.signal_id, "CLOSED", trade.reason, trade.to_dict())
        self.risk.sync_equity(self.broker.balance, self.broker.equity)
        self._equity_curve.append((snapshot.local_ts_ms, self.broker.equity))

        # One decision per second is easier to understand and avoids duplicate
        # orders from several depth updates describing the same market moment.
        if snapshot.local_ts_ms - self._last_decision_ts_ms >= 1000:
            self._last_decision_ts_ms = snapshot.local_ts_ms
            prediction = self.model.predict(frame)
            route = self.router.route(
                frame.regime, self.config.strategies.model_weight, self.config.strategies.rules_weight
            )
            signal = self.decision_engine.decide(frame, prediction, route)
            risk_decision = self.risk.evaluate(
                signal, snapshot, self.broker.open_positions_count(), route.size_multiplier
            )
            if risk_decision.allowed and not quality.healthy:
                risk_decision = RiskDecision(
                    False, "DATA_QUALITY",
                    "Качество рыночных данных недостаточно для безопасного входа.",
                    {"score": quality.score, "warnings": list(quality.warnings)},
                )
            self.last_prediction = prediction
            self.last_route = route
            self.last_signal = signal
            self.last_risk_decision = risk_decision
            self._signal_count += 1

            if risk_decision.allowed and not self.broker.position and not self.broker.pending_orders:
                quantity = self.risk.position_size(snapshot.mid, route.size_multiplier)
                order = self.broker.submit_signal(signal, quantity, snapshot)
                if order:
                    signal.status = "ORDERED"
                    self._ordered_count += 1
                    self.storage.save_decision(
                        signal.id, "ORDERED", risk_decision.message,
                        {"signal": signal.to_dict(), "risk": asdict(risk_decision), "order": asdict(order)},
                    )
                else:
                    signal.status = "SKIPPED"
            else:
                signal.status = "REJECTED" if signal.direction != Direction.FLAT else "OBSERVED"
                self._rejection_counts[risk_decision.code] += 1
                if signal.direction != Direction.FLAT:
                    self.storage.save_decision(
                        signal.id, "REJECTED", risk_decision.message,
                        {"signal": signal.to_dict(), "risk": asdict(risk_decision)},
                    )
            payload = signal.to_dict()
            self._recent_signals.appendleft(payload)
            self.storage.save_signal(payload)

        if snapshot.local_ts_ms - self._last_metric_ts_ms >= 10_000:
            self._last_metric_ts_ms = snapshot.local_ts_ms
            self.storage.save_metrics("runtime", self.status(compact=True))

    def reset_paper(self) -> dict[str, Any]:
        self.broker.reset()
        self.risk = RiskManager(self.config.risk, self.config.execution, self.config.model)
        self._equity_curve.clear()
        self._ordered_count = 0
        self._rejection_counts.clear()
        logger.warning("Paper account reset by user")
        return {"ok": True, "paper": self.broker.status()}

    def reset_kill_switch(self) -> dict[str, Any]:
        self.risk.reset_kill_switch()
        logger.warning("Risk kill switch reset by user")
        return {"ok": True, "risk": self.risk.status()}

    async def start_training(self, source: str = "synthetic", samples: int = 6000) -> dict[str, Any]:
        if self._training_task and not self._training_task.done():
            return {"ok": False, "message": "Обучение уже выполняется"}
        cfg = copy.deepcopy(self.config)
        source = "recorded" if source == "recorded" else "synthetic"
        samples = max(800, min(100_000, int(samples)))
        self.training_state = {
            "running": True, "stage": "queued", "progress": 0.0,
            "message": "Задача обучения создана", "source": source, "samples": samples,
        }
        run_id = self.storage.create_run("training", {"source": source, "samples": samples})

        def progress(payload: dict[str, object]) -> None:
            self.training_state = {"running": payload.get("stage") != "complete", **payload}

        async def worker() -> None:
            try:
                result = await asyncio.to_thread(train_model, cfg, source, samples, progress)
                self.training_state = {"running": False, "stage": "complete", "progress": 1.0, **result.to_dict()}
                self.storage.finish_run(run_id, "COMPLETED", result.to_dict())
                try:
                    self.model.load(str(MODEL_DIR / "best_model.pt"))
                except Exception:
                    logger.exception("New model was trained but could not be loaded")
            except asyncio.CancelledError:
                self.storage.finish_run(run_id, "CANCELLED", self.training_state)
                raise
            except Exception as exc:
                self.training_state = {
                    "running": False, "stage": "error", "progress": 0.0,
                    "message": f"Ошибка обучения: {exc}", "error": str(exc),
                }
                self.storage.finish_run(run_id, "FAILED", self.training_state)
                logger.exception("Training failed")

        self._training_task = asyncio.create_task(worker(), name="neuroscalper-training")
        return {"ok": True, "state": self.training_state}

    async def start_backtest(self, source: str = "synthetic", steps: int = 6000) -> dict[str, Any]:
        if self._backtest_task and not self._backtest_task.done():
            return {"ok": False, "message": "Бэктест уже выполняется"}
        cfg = copy.deepcopy(self.config)
        source = "recorded" if source == "recorded" else "synthetic"
        steps = max(500, min(2_000_000, int(steps)))
        self.backtest_state = {
            "running": True, "stage": "queued", "progress": 0.0,
            "message": "Задача бэктеста создана", "source": source, "steps": steps,
        }
        run_id = self.storage.create_run("backtest", {"source": source, "steps": steps})

        def progress(payload: dict[str, object]) -> None:
            self.backtest_state = {"running": payload.get("stage") != "complete", **payload}

        async def worker() -> None:
            try:
                result = await asyncio.to_thread(run_backtest, cfg, source, steps, 42, progress)
                self.backtest_state = {"running": False, "stage": "complete", "progress": 1.0, **result.to_dict()}
                self.storage.finish_run(run_id, "COMPLETED", result.to_dict())
                self.storage.save_metrics("backtest", result.metrics)
            except asyncio.CancelledError:
                self.storage.finish_run(run_id, "CANCELLED", self.backtest_state)
                raise
            except Exception as exc:
                self.backtest_state = {
                    "running": False, "stage": "error", "progress": 0.0,
                    "message": f"Ошибка бэктеста: {exc}", "error": str(exc),
                }
                self.storage.finish_run(run_id, "FAILED", self.backtest_state)
                logger.exception("Backtest failed")

        self._backtest_task = asyncio.create_task(worker(), name="neuroscalper-backtest")
        return {"ok": True, "state": self.backtest_state}

    @staticmethod
    def _downsample(points: deque[tuple[int, float]], limit: int = 300) -> list[list[float]]:
        rows = list(points)
        if len(rows) <= limit:
            return [[float(ts), float(value)] for ts, value in rows]
        stride = max(1, len(rows) // limit)
        return [[float(ts), float(value)] for ts, value in rows[::stride][-limit:]]

    def _orderbook_payload(self) -> dict[str, Any]:
        snapshot = self.last_snapshot
        if not snapshot:
            return {"bids": [], "asks": [], "mid": 0.0, "spread_bps": 0.0}
        max_qty = max(
            [level.quantity for level in snapshot.bids[:12] + snapshot.asks[:12]] or [1.0]
        )
        return {
            "mid": snapshot.mid,
            "spread_bps": snapshot.spread_bps,
            "bids": [
                {"price": level.price, "quantity": level.quantity, "strength": level.quantity / max_qty}
                for level in snapshot.bids[:12]
            ],
            "asks": [
                {"price": level.price, "quantity": level.quantity, "strength": level.quantity / max_qty}
                for level in snapshot.asks[:12]
            ],
        }

    def status(self, compact: bool = False) -> dict[str, Any]:
        frame_map = self.last_frame.as_map() if self.last_frame else {}
        uptime = (int(time.time() * 1000) - self.started_ts_ms) / 1000.0 if self.running else 0.0
        payload: dict[str, Any] = {
            "app": {
                "name": "CryptoHunter Neural Scalper",
                "version": "0.1.1",
                "running": self.running,
                "mode": self.mode,
                "source": self.source_label,
                "uptime_seconds": round(max(0.0, uptime), 1),
                "last_error": self.last_error,
                "live_orders_enabled": False,
                "safety_message": "Реальная отправка ордеров в этой версии заблокирована.",
            },
            "collector": self.collector_status,
            "market": {
                "symbol": self.config.market.symbol,
                "price": self.last_snapshot.mid if self.last_snapshot else 0.0,
                "spread_bps": self.last_snapshot.spread_bps if self.last_snapshot else 0.0,
                "regime": self.last_frame.regime if self.last_frame else "WAITING",
                "latency_ms": frame_map.get("latency_ms", 0.0),
                "liquidity_score": frame_map.get("liquidity_score", 0.0),
                "obi_10": frame_map.get("obi_10", 0.0),
                "trade_imbalance_20": frame_map.get("trade_imbalance_20", 0.0),
                "snapshot_count": self._snapshot_count,
                "data_quality": self.data_quality.status(),
            },
            "model": self.model.status(),
            "paper": self.broker.status(),
            "risk": self.risk.status(),
            "runtime": {
                "signals": self._signal_count,
                "orders": self._ordered_count,
                "rejections": dict(self._rejection_counts.most_common(12)),
            },
            "training": self.training_state,
            "backtest": self.backtest_state,
        }
        if compact:
            return payload
        payload.update({
            "config": config_to_dict(self.config),
            "last_signal": self.last_signal.to_dict() if self.last_signal else None,
            "last_risk_decision": asdict(self.last_risk_decision) if self.last_risk_decision else None,
            "last_route": asdict(self.last_route) if self.last_route else None,
            "recent_signals": list(self._recent_signals)[:30],
            "orderbook": self._orderbook_payload(),
            "charts": {
                "equity": self._downsample(self._equity_curve),
                "price": self._downsample(self._price_curve),
            },
            "system": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "torch": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                "database": str(self.storage.path),
                "models_dir": str(MODEL_DIR),
                "reports_dir": str(REPORT_DIR),
            },
        })
        return payload

    def history(self) -> dict[str, Any]:
        return {
            "signals": self.storage.recent_signals(60),
            "trades": self.storage.recent_trades(100),
            "decisions": self.storage.recent_decisions(120),
            "logs": memory_handler.tail(200),
            "strategies": StrategyEnsemble.catalog(),
        }
