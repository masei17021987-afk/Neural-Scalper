from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import DATA_DIR, ensure_runtime_dirs


@dataclass(slots=True)
class MarketConfig:
    exchange: str = "binance"
    symbol: str = "BTCUSDT"
    depth_levels: int = 20
    update_ms: int = 100
    record_raw_events: bool = True
    record_features: bool = True
    stale_after_ms: int = 1500


@dataclass(slots=True)
class ModelConfig:
    architecture: str = "lob_gru"
    sequence_length: int = 64
    hidden_size: int = 96
    dropout: float = 0.15
    min_confidence: float = 0.62
    min_net_edge_bps: float = 1.2
    checkpoint: str = ""
    use_gpu: bool = True
    mixed_precision: bool = True
    batch_size: int = 128
    epochs: int = 8
    learning_rate: float = 0.0008


@dataclass(slots=True)
class ExecutionConfig:
    mode: str = "paper"
    preferred_order_type: str = "adaptive"
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    assumed_latency_ms: int = 65
    queue_factor: float = 0.65
    cancel_after_ms: int = 900
    slippage_bps: float = 0.5
    max_spread_bps: float = 4.0


@dataclass(slots=True)
class RiskConfig:
    initial_balance: float = 10_000.0
    risk_per_trade_pct: float = 0.25
    max_position_notional_pct: float = 10.0
    max_open_positions: int = 1
    max_daily_loss_pct: float = 2.0
    max_drawdown_pct: float = 10.0
    max_consecutive_losses: int = 5
    cooldown_seconds: int = 20
    stop_loss_bps: float = 18.0
    take_profit_bps: float = 30.0
    trailing_activation_bps: float = 18.0
    trailing_distance_bps: float = 10.0
    max_holding_seconds: int = 180
    allow_dca: bool = False


@dataclass(slots=True)
class StrategyConfig:
    pulse_enabled: bool = True
    drops_enabled: bool = True
    pumps_enabled: bool = True
    liquidations_enabled: bool = True
    volume_enabled: bool = True
    spread_enabled: bool = True
    waves_enabled: bool = True
    model_weight: float = 0.55
    rules_weight: float = 0.45


@dataclass(slots=True)
class AppConfig:
    market: MarketConfig = field(default_factory=MarketConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategies: StrategyConfig = field(default_factory=StrategyConfig)
    language: str = "ru"
    theme: str = "graphite"
    first_run_complete: bool = False


DEFAULT_CONFIG_PATH = DATA_DIR / "config.json"


def _merge_dataclass(instance: Any, payload: dict[str, Any]) -> Any:
    for key, value in payload.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)
    return instance


def validate_config(config: AppConfig) -> AppConfig:
    config.market.symbol = "".join(ch for ch in str(config.market.symbol).upper() if ch.isalnum()) or "BTCUSDT"
    config.market.depth_levels = max(5, min(100, int(config.market.depth_levels)))
    config.market.update_ms = 100 if int(config.market.update_ms) <= 100 else 250
    config.model.sequence_length = max(16, min(512, int(config.model.sequence_length)))
    config.model.hidden_size = max(32, min(512, int(config.model.hidden_size)))
    config.model.min_confidence = max(0.34, min(0.99, float(config.model.min_confidence)))
    config.model.min_net_edge_bps = max(0.0, min(100.0, float(config.model.min_net_edge_bps)))
    config.model.batch_size = max(8, min(4096, int(config.model.batch_size)))
    config.model.epochs = max(1, min(200, int(config.model.epochs)))
    config.execution.mode = "paper" if config.execution.mode not in {"paper", "demo", "testnet"} else config.execution.mode
    config.execution.maker_fee_bps = max(0.0, float(config.execution.maker_fee_bps))
    config.execution.taker_fee_bps = max(0.0, float(config.execution.taker_fee_bps))
    config.execution.assumed_latency_ms = max(0, min(5000, int(config.execution.assumed_latency_ms)))
    config.execution.queue_factor = max(0.0, min(1.0, float(config.execution.queue_factor)))
    config.execution.max_spread_bps = max(0.1, min(100.0, float(config.execution.max_spread_bps)))
    config.risk.initial_balance = max(10.0, float(config.risk.initial_balance))
    config.risk.risk_per_trade_pct = max(0.01, min(5.0, float(config.risk.risk_per_trade_pct)))
    config.risk.max_position_notional_pct = max(0.1, min(100.0, float(config.risk.max_position_notional_pct)))
    config.risk.max_daily_loss_pct = max(0.1, min(50.0, float(config.risk.max_daily_loss_pct)))
    config.risk.max_drawdown_pct = max(0.1, min(90.0, float(config.risk.max_drawdown_pct)))
    config.risk.max_consecutive_losses = max(1, min(100, int(config.risk.max_consecutive_losses)))
    config.risk.cooldown_seconds = max(0, min(86_400, int(config.risk.cooldown_seconds)))
    config.risk.stop_loss_bps = max(1.0, min(5000.0, float(config.risk.stop_loss_bps)))
    config.risk.take_profit_bps = max(1.0, min(10_000.0, float(config.risk.take_profit_bps)))
    config.risk.max_holding_seconds = max(1, min(86_400, int(config.risk.max_holding_seconds)))
    total_weight = float(config.strategies.model_weight) + float(config.strategies.rules_weight)
    if total_weight <= 0:
        config.strategies.model_weight, config.strategies.rules_weight = 0.55, 0.45
    else:
        config.strategies.model_weight = float(config.strategies.model_weight) / total_weight
        config.strategies.rules_weight = float(config.strategies.rules_weight) / total_weight
    return config


def load_config(path: Path | None = None) -> AppConfig:
    ensure_runtime_dirs()
    target = path or DEFAULT_CONFIG_PATH
    config = AppConfig()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            _merge_dataclass(config, payload)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    config = validate_config(config)
    if not target.exists():
        save_config(config, target)
    return config


def save_config(config: AppConfig, path: Path | None = None) -> None:
    ensure_runtime_dirs()
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(validate_config(copy.deepcopy(config)))
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return asdict(config)


def update_config(config: AppConfig, patch: dict[str, Any]) -> AppConfig:
    updated = copy.deepcopy(config)
    _merge_dataclass(updated, patch)
    return validate_config(updated)
