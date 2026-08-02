from __future__ import annotations

from pathlib import Path

import pytest

from neuroscalper.config import AppConfig
from neuroscalper.domain import Direction, OrderType, TradingSignal
from neuroscalper.execution.paper import PaperBroker
from neuroscalper.market.synthetic import SyntheticMarket


def _signal(ts_ms: int) -> TradingSignal:
    return TradingSignal(
        id="signal-1", symbol="BTCUSDT", ts_ms=ts_ms, direction=Direction.LONG,
        confidence=0.9, expected_gross_edge_bps=30.0, expected_net_edge_bps=15.0,
        order_type=OrderType.MARKET, reasons=["test"], warnings=[], regime="TREND_UP",
        model={}, votes=[],
    )


def test_paper_balance_and_trade_pnl_include_entry_and_exit_fees(tmp_path: Path):
    cfg = AppConfig()
    cfg.execution.assumed_latency_ms = 0
    cfg.execution.slippage_bps = 0.0
    cfg.execution.taker_fee_bps = 5.0
    cfg.risk.stop_loss_bps = 5000.0
    cfg.risk.take_profit_bps = 5000.0
    broker = PaperBroker(cfg.execution, cfg.risk, tmp_path / "paper.json", restore=False)
    snapshot = SyntheticMarket(seed=4).step()
    order = broker.submit_signal(_signal(snapshot.local_ts_ms), 0.01, snapshot)
    assert order is not None
    broker.on_snapshot(snapshot)
    assert broker.position is not None
    initial = cfg.risk.initial_balance
    trade = broker.close_position(snapshot, "TEST_CLOSE")
    assert trade is not None
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.fees)
    assert broker.balance == pytest.approx(initial + trade.net_pnl)
