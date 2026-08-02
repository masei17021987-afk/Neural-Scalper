from __future__ import annotations

import copy

from neuroscalper.config import AppConfig
from neuroscalper.risk.manager import RiskManager


def test_drawdown_is_measured_from_high_water_mark():
    config = AppConfig()
    config.risk.max_drawdown_pct = 10.0
    manager = RiskManager(config.risk, config.execution, config.model)
    manager.sync_equity(20_000.0, 20_000.0)
    manager.sync_equity(17_500.0, 17_500.0)
    assert manager.state.kill_switch is True
    assert "MAX_DRAWDOWN" in manager.state.kill_reason


def test_losing_equity_does_not_lower_peak():
    config = AppConfig()
    manager = RiskManager(config.risk, config.execution, config.model)
    manager.sync_equity(15_000.0, 15_000.0)
    manager.sync_equity(12_000.0, 12_000.0)
    assert manager.state.peak_equity == 15_000.0
