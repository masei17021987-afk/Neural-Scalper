from __future__ import annotations

import dataclasses

import pytest

from neuroscalper.features.microstructure import MicrostructureFeatureEngine
from neuroscalper.market.orderbook import LocalOrderBook, OrderBookGap
from neuroscalper.market.synthetic import SyntheticMarket


def test_futures_orderbook_bridges_snapshot_and_detects_gap():
    book = LocalOrderBook("BTCUSDT")
    book.set_snapshot({"lastUpdateId": 10, "bids": [["100", "2"]], "asks": [["101", "3"]]})
    assert book.apply_diff({"U": 11, "u": 12, "pu": 10, "E": 1000, "b": [["100", "4"]], "a": []})
    assert book.last_update_id == 12
    assert book.bids[100.0] == 4.0
    with pytest.raises(OrderBookGap):
        book.apply_diff({"U": 13, "u": 14, "pu": 11, "E": 1001, "b": [], "a": []})


def test_feature_engine_counts_trade_event_only_once():
    market = SyntheticMarket(seed=7)
    engine = MicrostructureFeatureEngine(levels=20, sequence_length=16)
    snapshot = market.step()
    engine.update(snapshot)
    duplicate = dataclasses.replace(
        snapshot,
        exchange_ts_ms=snapshot.exchange_ts_ms + 50,
        local_ts_ms=snapshot.local_ts_ms + 50,
        sequence=snapshot.sequence + 1,
    )
    engine.update(duplicate)
    assert len(engine.signed_trades) == 1
    assert engine.last_trade_ts == snapshot.last_trade_ts_ms
