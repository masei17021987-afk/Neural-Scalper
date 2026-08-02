from __future__ import annotations

import math
import uuid
from dataclasses import asdict

from .config import AppConfig
from .domain import Direction, FeatureFrame, ModelPrediction, OrderType, TradingSignal
from .models.router import RouterDecision
from .strategies.ensemble import StrategyEnsemble


class DecisionEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.strategies = StrategyEnsemble(config.strategies)

    def update_config(self, config: AppConfig) -> None:
        self.config = config
        self.strategies = StrategyEnsemble(config.strategies)

    def _order_type(self, router: RouterDecision, confidence: float) -> OrderType:
        preferred = self.config.execution.preferred_order_type.lower()
        if preferred == "market":
            return OrderType.MARKET
        if preferred in {"post_only", "post-only"}:
            return OrderType.POST_ONLY
        if preferred == "limit":
            return OrderType.LIMIT
        if router.execution_style == "AGGRESSIVE" and confidence >= 0.72:
            return OrderType.MARKET
        return OrderType.POST_ONLY

    def _cost_bps(self, order_type: OrderType, spread_bps: float) -> float:
        execution = self.config.execution
        if order_type == OrderType.MARKET:
            return 2.0 * execution.taker_fee_bps + spread_bps + 2.0 * execution.slippage_bps
        return execution.maker_fee_bps + execution.taker_fee_bps + 0.25 * spread_bps + execution.slippage_bps

    def decide(self, frame: FeatureFrame, prediction: ModelPrediction, router: RouterDecision) -> TradingSignal:
        feature_map = frame.as_map()
        rules_score, rules_confidence, votes = self.strategies.evaluate(frame)
        model_score = prediction.probabilities.get("LONG", 0.0) - prediction.probabilities.get("SHORT", 0.0)
        combined = router.model_weight * model_score + router.rules_weight * rules_score
        class_confidence = max(prediction.probabilities.get("LONG", 0.0), prediction.probabilities.get("SHORT", 0.0))
        confidence = max(0.0, min(0.99,
            0.42 * class_confidence
            + 0.26 * rules_confidence
            + 0.32 * min(1.0, abs(combined) * 1.8)
        ))

        threshold = 0.12
        if combined > threshold:
            direction = Direction.LONG
        elif combined < -threshold:
            direction = Direction.SHORT
        else:
            direction = Direction.FLAT

        order_type = self._order_type(router, confidence)
        model_edge_direction = 1.0 if prediction.expected_edge_bps >= 0 else -1.0
        intended_sign = 1.0 if direction == Direction.LONG else -1.0 if direction == Direction.SHORT else 0.0
        agreement = 1.0 if intended_sign and model_edge_direction == intended_sign else 0.45
        movement_proxy = (
            abs(feature_map.get("return_10_bps", 0.0)) * 0.7
            + abs(feature_map.get("microprice_delta_bps", 0.0)) * 1.8
            + feature_map.get("realized_vol_30_bps", 0.0) * 1.5
        )
        gross_edge = (
            abs(prediction.expected_edge_bps) * 0.65 + movement_proxy * 0.35
        ) * agreement * max(0.25, confidence)
        cost = self._cost_bps(order_type, feature_map.get("spread_bps", 0.0))
        net_edge = gross_edge - cost

        aligned = sorted(
            [vote for vote in votes if direction != Direction.FLAT and vote.score * intended_sign > 0],
            key=lambda vote: abs(vote.score) * vote.confidence,
            reverse=True,
        )
        opposing = sorted(
            [vote for vote in votes if direction != Direction.FLAT and vote.score * intended_sign < 0],
            key=lambda vote: abs(vote.score) * vote.confidence,
            reverse=True,
        )
        reasons = [vote.reason for vote in aligned[:4]]
        if direction != Direction.FLAT:
            reasons.insert(0, f"Совокупный сигнал: {combined:+.2f}; режим {router.regime}.")
            reasons.append(f"Оценка движения до расходов: {gross_edge:.2f} б.п.")
        else:
            reasons = ["Сигналы нейросети и правил не дают достаточного перевеса."]
        warnings = [vote.reason for vote in opposing[:3]]
        if net_edge < self.config.model.min_net_edge_bps:
            warnings.append(
                f"После расходов остаётся {net_edge:.2f} б.п.; требуется минимум {self.config.model.min_net_edge_bps:.2f}."
            )
        if router.execution_style == "BLOCK":
            warnings.append("Роутер режима рынка запрещает вход из-за плохой ликвидности.")
            direction = Direction.FLAT
        if confidence < self.config.model.min_confidence:
            direction = Direction.FLAT
        if net_edge < self.config.model.min_net_edge_bps:
            direction = Direction.FLAT

        return TradingSignal(
            id=uuid.uuid4().hex,
            symbol=frame.symbol,
            ts_ms=frame.local_ts_ms,
            direction=direction,
            confidence=confidence,
            expected_gross_edge_bps=gross_edge,
            expected_net_edge_bps=net_edge,
            order_type=order_type,
            reasons=reasons,
            warnings=warnings,
            regime=router.regime,
            model={
                "name": prediction.model_name,
                "ready": prediction.model_ready,
                "probabilities": prediction.probabilities,
                "expected_edge_bps": prediction.expected_edge_bps,
                "expected_volatility_bps": prediction.expected_volatility_bps,
                "combined_score": combined,
                "model_score": model_score,
                "rules_score": rules_score,
                "router": asdict(router),
            },
            votes=StrategyEnsemble.votes_to_dict(votes),
        )
