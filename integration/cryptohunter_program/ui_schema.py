UI_SCHEMA = {
    "groups": [
        {"id": "market", "title": "Рынок", "fields": ["symbol", "depth_levels", "sequence_length"]},
        {"id": "model", "title": "Нейросеть", "fields": ["min_confidence", "min_net_edge_bps"]},
        {"id": "risk", "title": "Риск", "fields": ["risk_per_trade_pct", "max_drawdown_pct", "max_daily_loss_pct"]},
        {"id": "execution", "title": "Исполнение", "fields": ["preferred_order_type", "paper_only"]},
    ],
    "warnings": [
        "Программа работает только в paper-режиме.",
        "Публичные market-data не требуют exchange API key.",
    ],
}
