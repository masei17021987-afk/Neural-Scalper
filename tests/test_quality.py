from __future__ import annotations

import dataclasses

from neuroscalper.market.quality import DataQualityMonitor
from neuroscalper.market.synthetic import SyntheticMarket


def test_crossed_book_is_fail_closed():
    snapshot = SyntheticMarket(seed=12).step()
    broken = dataclasses.replace(snapshot, bids=snapshot.asks, asks=snapshot.bids)
    monitor = DataQualityMonitor()
    state = monitor.update(broken)
    assert state.healthy is False
    assert state.crossed_books == 1
