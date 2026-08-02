from __future__ import annotations

from neuroscalper.backtest.engine import run_backtest
from neuroscalper.config import AppConfig


def test_event_backtest_completes_and_reports_cost_aware_metrics():
    config = AppConfig()
    result = run_backtest(config, source="synthetic", steps=800, seed=9)
    assert result.steps == 800
    assert "max_drawdown_pct" in result.metrics
    assert "fill_rate_pct" in result.metrics
    assert result.metrics["signals"] > 0
    assert len(result.equity_curve) > 1
