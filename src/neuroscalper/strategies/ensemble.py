from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..config import StrategyConfig
from ..domain import FeatureFrame, StrategyVote
from .components import ALL_COMPONENTS


class StrategyEnsemble:
    WEIGHTS = {
        "pulse": 1.15,
        "drops": 0.85,
        "pumps": 0.75,
        "liquidations": 0.95,
        "volume": 1.05,
        "spread": 0.75,
        "waves": 0.85,
    }

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def _enabled(self, strategy_id: str) -> bool:
        return bool(getattr(self.config, f"{strategy_id}_enabled", True))

    def evaluate(self, frame: FeatureFrame) -> tuple[float, float, list[StrategyVote]]:
        votes = [component.evaluate(frame) for strategy_id, component in ALL_COMPONENTS.items() if self._enabled(strategy_id)]
        if not votes:
            return 0.0, 0.0, []
        weighted_score = 0.0
        weight_total = 0.0
        confidence_sum = 0.0
        for vote in votes:
            weight = self.WEIGHTS.get(vote.strategy_id, 1.0) * (0.35 + 0.65 * vote.confidence)
            weighted_score += vote.score * weight
            weight_total += weight
            confidence_sum += vote.confidence
        score = weighted_score / max(weight_total, 1e-12)
        confidence = confidence_sum / len(votes)
        return max(-1.0, min(1.0, score)), max(0.0, min(1.0, confidence)), votes

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        return [
            {
                "id": component.id,
                "title": component.title,
                "description": component.description,
                "weight": StrategyEnsemble.WEIGHTS.get(component.id, 1.0),
            }
            for component in ALL_COMPONENTS.values()
        ]

    @staticmethod
    def votes_to_dict(votes: list[StrategyVote]) -> list[dict[str, Any]]:
        return [asdict(vote) for vote in votes]
