"""Closed configuration surface for the CryptoHunter program slot."""

DEFAULT_CONFIG = {
    "symbol": "BTCUSDT",
    "depth_levels": 20,
    "sequence_length": 64,
    "min_confidence": 0.62,
    "min_net_edge_bps": 1.2,
    "risk_per_trade_pct": 0.25,
    "max_drawdown_pct": 10.0,
    "max_daily_loss_pct": 2.0,
    "preferred_order_type": "adaptive",
    "paper_only": True,
}

CONFIG_SCHEMA = {
    "symbol": {"type": "symbol", "required": True},
    "depth_levels": {"type": "integer", "min": 5, "max": 100},
    "sequence_length": {"type": "integer", "min": 16, "max": 512},
    "min_confidence": {"type": "number", "min": 0.34, "max": 0.99},
    "min_net_edge_bps": {"type": "number", "min": 0.0, "max": 100.0},
    "risk_per_trade_pct": {"type": "number", "min": 0.01, "max": 5.0},
    "max_drawdown_pct": {"type": "number", "min": 0.1, "max": 90.0},
    "max_daily_loss_pct": {"type": "number", "min": 0.1, "max": 50.0},
    "preferred_order_type": {"type": "choice", "values": ["adaptive", "post_only", "limit", "market"]},
    "paper_only": {"type": "boolean", "const": True},
}
