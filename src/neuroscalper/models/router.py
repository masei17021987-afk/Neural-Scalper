from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import DATA_DIR


@dataclass(slots=True)
class ExpertMemory:
    mean_reward: float = 0.0
    samples: int = 0

    def update(self, reward: float, alpha: float = 0.08) -> None:
        if self.samples == 0:
            self.mean_reward = reward
        else:
            self.mean_reward = (1.0 - alpha) * self.mean_reward + alpha * reward
        self.samples += 1


@dataclass(slots=True)
class RouterDecision:
    regime: str
    model_weight: float
    rules_weight: float
    execution_style: str
    size_multiplier: float
    explanation: str
    expert_scores: dict[str, float] = field(default_factory=dict)


class HierarchicalRegimeRouter:
    """Low-level experts + high-level regime selector with bounded memory."""

    BASE = {
        "RANGE": (0.42, 0.58, "PASSIVE", 0.70),
        "TREND_UP": (0.60, 0.40, "ADAPTIVE", 1.00),
        "TREND_DOWN": (0.60, 0.40, "ADAPTIVE", 1.00),
        "BREAKOUT_UP": (0.66, 0.34, "AGGRESSIVE", 0.85),
        "BREAKOUT_DOWN": (0.66, 0.34, "AGGRESSIVE", 0.85),
        "HIGH_VOL": (0.52, 0.48, "CAUTIOUS", 0.45),
        "LOW_LIQUIDITY": (0.35, 0.65, "BLOCK", 0.0),
    }

    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or (DATA_DIR / "router_memory.json")
        self.memory: dict[str, ExpertMemory] = {}
        self.load()

    def load(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            payload = {}
        for key, row in payload.items() if isinstance(payload, dict) else []:
            if isinstance(row, dict):
                self.memory[key] = ExpertMemory(float(row.get("mean_reward", 0.0)), int(row.get("samples", 0)))

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: {"mean_reward": value.mean_reward, "samples": value.samples} for key, value in self.memory.items()}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def route(self, regime: str, configured_model_weight: float, configured_rules_weight: float) -> RouterDecision:
        base_model, base_rules, style, size = self.BASE.get(regime, self.BASE["RANGE"])
        memory = self.memory.get(regime, ExpertMemory())
        adjustment = math.tanh(memory.mean_reward / 10.0) * min(0.12, memory.samples / 5000.0)
        model = max(0.15, min(0.85, 0.5 * base_model + 0.5 * configured_model_weight + adjustment))
        rules = max(0.15, min(0.85, 0.5 * base_rules + 0.5 * configured_rules_weight - adjustment))
        total = model + rules
        model, rules = model / total, rules / total
        explanation = {
            "RANGE": "Боковик: больше веса проверяемым микроструктурным правилам.",
            "TREND_UP": "Устойчивый восходящий поток: нейросеть получает больший вес.",
            "TREND_DOWN": "Устойчивый нисходящий поток: нейросеть получает больший вес.",
            "BREAKOUT_UP": "Пробой вверх: вход быстрее, но размер позиции снижен.",
            "BREAKOUT_DOWN": "Пробой вниз: вход быстрее, но размер позиции снижен.",
            "HIGH_VOL": "Высокая волатильность: размер позиции сильно ограничен.",
            "LOW_LIQUIDITY": "Плохая ликвидность: новые входы заблокированы.",
        }.get(regime, "Нейтральный режим рынка.")
        return RouterDecision(
            regime=regime,
            model_weight=model,
            rules_weight=rules,
            execution_style=style,
            size_multiplier=size,
            explanation=explanation,
            expert_scores={"historical_reward": memory.mean_reward, "samples": float(memory.samples)},
        )

    def update(self, regime: str, net_pnl_bps: float) -> None:
        memory = self.memory.setdefault(regime, ExpertMemory())
        memory.update(float(net_pnl_bps))
        self.save()
