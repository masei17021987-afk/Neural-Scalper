from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import BookSnapshot


@dataclass(slots=True)
class DataQualityState:
    score: float = 1.0
    healthy: bool = True
    warnings: list[str] = field(default_factory=list)
    sequence_gaps: int = 0
    crossed_books: int = 0
    stale_events: int = 0
    price_outliers: int = 0
    last_sequence: int = 0
    last_mid: float = 0.0


class DataQualityMonitor:
    """Fail-closed quality checks shared by public market and paper execution."""

    def __init__(self, stale_after_ms: int = 1500) -> None:
        self.stale_after_ms = max(100, int(stale_after_ms))
        self.state = DataQualityState()

    def update(self, snapshot: BookSnapshot) -> DataQualityState:
        warnings: list[str] = []
        penalty = 0.0
        if not snapshot.bids or not snapshot.asks:
            warnings.append("Стакан не содержит обе стороны.")
            penalty += 1.0
        elif snapshot.best_bid >= snapshot.best_ask:
            self.state.crossed_books += 1
            warnings.append("Лучший bid пересёк лучший ask.")
            penalty += 0.8

        if self.state.last_sequence and snapshot.sequence:
            if snapshot.sequence <= self.state.last_sequence:
                warnings.append("Последовательность стакана не увеличилась.")
                penalty += 0.25
            elif snapshot.sequence > self.state.last_sequence + 100_000:
                self.state.sequence_gaps += 1
                warnings.append("Обнаружен подозрительно большой разрыв последовательности.")
                penalty += 0.55

        latency = max(0, snapshot.local_ts_ms - snapshot.exchange_ts_ms)
        if latency > self.stale_after_ms:
            self.state.stale_events += 1
            warnings.append(f"Высокая задержка данных: {latency} мс.")
            penalty += min(0.75, latency / max(self.stale_after_ms, 1) * 0.25)

        if self.state.last_mid > 0 and snapshot.mid > 0:
            jump_bps = abs(snapshot.mid / self.state.last_mid - 1.0) * 10_000.0
            if jump_bps > 250.0:
                self.state.price_outliers += 1
                warnings.append(f"Подозрительный скачок цены: {jump_bps:.1f} б.п.")
                penalty += 0.7

        score = max(0.0, min(1.0, 1.0 - penalty))
        self.state.score = score
        self.state.healthy = score >= 0.55
        self.state.warnings = warnings
        self.state.last_sequence = max(self.state.last_sequence, int(snapshot.sequence or 0))
        self.state.last_mid = snapshot.mid or self.state.last_mid
        return self.state

    def status(self) -> dict[str, object]:
        return {
            "score": self.state.score,
            "healthy": self.state.healthy,
            "warnings": list(self.state.warnings),
            "sequence_gaps": self.state.sequence_gaps,
            "crossed_books": self.state.crossed_books,
            "stale_events": self.state.stale_events,
            "price_outliers": self.state.price_outliers,
        }
