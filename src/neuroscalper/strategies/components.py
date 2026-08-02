from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Mapping

from ..domain import FeatureFrame, StrategyVote


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


class StrategyComponent(ABC):
    id: str
    title: str
    description: str

    @abstractmethod
    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        raise NotImplementedError

    def vote(self, score: float, confidence: float, reason: str, **metadata: float | str | bool) -> StrategyVote:
        return StrategyVote(self.id, _clip(score), _clip(confidence, 0.0, 1.0), reason, dict(metadata))


class PulseComponent(StrategyComponent):
    id = "pulse"
    title = "Импульс"
    description = "Ищет синхронный рывок цены, сделок и объёма."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        raw = (
            0.35 * math.tanh(f["return_3_bps"] / 3.0)
            + 0.32 * f["trade_imbalance_20"]
            + 0.20 * math.tanh(f["volume_acceleration"])
            + 0.13 * math.tanh(f["microprice_delta_bps"] / 1.2)
        )
        confidence = min(1.0, abs(raw) + 0.25 * min(1.0, abs(f["return_3_bps"]) / 4.0))
        direction = "покупателей" if raw > 0 else "продавцов"
        return self.vote(raw, confidence, f"Краткий импульс на стороне {direction}.")


class DropsComponent(StrategyComponent):
    id = "drops"
    title = "Отскок после падения"
    description = "Ищет безопасный разворот после резкого снижения, не ловит продолжающееся падение."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        drop = max(0.0, -f["return_10_bps"] / 10.0)
        reset = max(0.0, f["return_1_bps"] / 2.0) + max(0.0, f["microprice_delta_bps"] / 1.5)
        flow = max(0.0, f["trade_imbalance_5"])
        falling_knife = max(0.0, -f["return_3_bps"] / 4.0) + max(0.0, -f["trade_imbalance_20"])
        long_score = math.tanh(drop * (0.5 + reset + flow) - falling_knife)
        confidence = min(1.0, drop * 0.5 + reset * 0.25 + flow * 0.25)
        reason = "Есть падение и признаки разворота вверх." if long_score > 0.12 else "Отскок после падения пока не подтверждён."
        return self.vote(long_score if long_score > 0.05 else 0.0, confidence, reason)


class PumpsComponent(StrategyComponent):
    id = "pumps"
    title = "Памп / истощение"
    description = "Различает продолжение импульса и истощение резкого роста."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        pump = max(0.0, f["return_10_bps"] / 10.0)
        continuation = max(0.0, f["trade_imbalance_20"]) + max(0.0, f["microprice_delta_bps"] / 2.0)
        exhaustion = max(0.0, -f["return_1_bps"] / 2.0) + max(0.0, -f["trade_imbalance_5"])
        score = math.tanh(pump * continuation - pump * exhaustion * 1.15)
        if pump > 0.4 and exhaustion > continuation:
            score = -math.tanh(pump * (exhaustion - continuation))
            reason = "Рост выдыхается: поток начал разворачиваться вниз."
        elif score > 0:
            reason = "Рост поддержан агрессивными покупками."
        else:
            reason = "Сильного подтверждённого пампа нет."
        confidence = min(1.0, pump * 0.55 + abs(continuation - exhaustion) * 0.3)
        return self.vote(score, confidence, reason)


class LiquidationsComponent(StrategyComponent):
    id = "liquidations"
    title = "Каскад ликвидаций"
    description = "Использует принудительные закрытия как контекст, а не как слепой сигнал."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        sell_liq = f["liquidation_sell_pressure"]
        buy_liq = f["liquidation_buy_pressure"]
        reversal_up = max(0.0, f["microprice_delta_bps"] / 1.5) + max(0.0, f["trade_imbalance_5"])
        reversal_down = max(0.0, -f["microprice_delta_bps"] / 1.5) + max(0.0, -f["trade_imbalance_5"])
        continuation_down = sell_liq * max(0.0, -f["trade_imbalance_20"])
        continuation_up = buy_liq * max(0.0, f["trade_imbalance_20"])
        score = sell_liq * reversal_up - buy_liq * reversal_down + 0.4 * (continuation_up - continuation_down)
        confidence = min(1.0, max(sell_liq, buy_liq) * (0.5 + abs(score)))
        if sell_liq > 0.05 and score > 0:
            reason = "Ликвидации лонгов поглощены покупателями — возможен отскок."
        elif buy_liq > 0.05 and score < 0:
            reason = "Ликвидации шортов поглощены продавцами — возможен откат."
        elif max(sell_liq, buy_liq) > 0.05:
            reason = "Каскад есть, но направление ещё не подтверждено стаканом."
        else:
            reason = "Значимого каскада ликвидаций нет."
        return self.vote(score, confidence, reason)


class VolumeComponent(StrategyComponent):
    id = "volume"
    title = "Поток объёма"
    description = "Сравнивает агрессивные покупки и продажи на нескольких окнах."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        score = 0.45 * f["trade_imbalance_5"] + 0.35 * f["trade_imbalance_20"] + 0.20 * f["trade_imbalance_50"]
        score *= 0.7 + 0.3 * min(1.0, max(0.0, f["volume_acceleration"] + 1.0))
        confidence = min(1.0, abs(score) + 0.2 * abs(f["volume_acceleration"]))
        reason = "Покупки доминируют в потоке сделок." if score > 0 else "Продажи доминируют в потоке сделок."
        return self.vote(score, confidence, reason)


class SpreadComponent(StrategyComponent):
    id = "spread"
    title = "Спред и ликвидность"
    description = "Блокирует дорогие входы и повышает доверие к плотному стакану."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        directional = math.tanh(f["microprice_delta_bps"] / 1.5) * f["liquidity_score"]
        spread_penalty = min(1.0, f["spread_bps"] / 6.0)
        score = directional * (1.0 - spread_penalty)
        confidence = max(0.0, min(1.0, f["liquidity_score"] * (1.0 - spread_penalty)))
        reason = "Стакан плотный, цена входа приемлема." if confidence > 0.55 else "Спред или глубина стакана ухудшают качество входа."
        return self.vote(score, confidence, reason, spread_bps=f["spread_bps"])


class WavesComponent(StrategyComponent):
    id = "waves"
    title = "Микроволны"
    description = "Оценивает согласованность короткого и среднего движения."

    def evaluate(self, frame: FeatureFrame) -> StrategyVote:
        f = frame.as_map()
        alignment = (
            math.tanh(f["return_3_bps"] / 3.0)
            + math.tanh(f["return_10_bps"] / 6.0)
            + math.tanh(f["return_30_bps"] / 10.0)
        ) / 3.0
        score = alignment * (0.6 + 0.4 * abs(f["momentum_quality"]))
        confidence = min(1.0, abs(alignment) + 0.25 * abs(f["momentum_quality"]))
        reason = "Короткая и средняя волна направлены одинаково." if abs(alignment) > 0.25 else "Волны рынка спорят между собой."
        return self.vote(score, confidence, reason)


ALL_COMPONENTS = {
    component.id: component
    for component in (
        PulseComponent(),
        DropsComponent(),
        PumpsComponent(),
        LiquidationsComponent(),
        VolumeComponent(),
        SpreadComponent(),
        WavesComponent(),
    )
}
