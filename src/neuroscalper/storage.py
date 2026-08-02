from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .paths import DATA_DIR, ensure_runtime_dirs


class Storage:
    """Small durable store for UI, audit trail and crash recovery."""

    def __init__(self, path: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.path = path or (DATA_DIR / "neuroscalper.db")
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                ts_ms INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                confidence REAL NOT NULL,
                net_edge_bps REAL NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                closed_ts_ms INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                net_pnl REAL NOT NULL,
                return_pct REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_ts_ms INTEGER NOT NULL,
                finished_ts_ms INTEGER,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_ms INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_ms INTEGER NOT NULL,
                signal_id TEXT,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
        ]
        with self._lock, self._connection:
            for statement in statements:
                self._connection.execute(statement)
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts_ms DESC)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(closed_ts_ms DESC)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts_ms DESC)")

    @staticmethod
    def _json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    def save_signal(self, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO signals(id, ts_ms, symbol, direction, confidence, net_edge_bps, status, payload_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload_json=excluded.payload_json
                """,
                (
                    payload["id"], int(payload["ts_ms"]), payload["symbol"], payload["direction"],
                    float(payload["confidence"]), float(payload["expected_net_edge_bps"]),
                    payload.get("status", "CREATED"), self._json(payload),
                ),
            )

    def save_trade(self, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO trades(id, closed_ts_ms, symbol, direction, net_pnl, return_pct, payload_json)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    payload["id"], int(payload["closed_ts_ms"]), payload["symbol"], payload["direction"],
                    float(payload["net_pnl"]), float(payload["return_pct"]), self._json(payload),
                ),
            )

    def save_decision(self, signal_id: str | None, action: str, reason: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO decisions(ts_ms, signal_id, action, reason, payload_json) VALUES(?,?,?,?,?)",
                (int(time.time() * 1000), signal_id, action, reason, self._json(payload)),
            )

    def save_metrics(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO metrics(ts_ms, kind, payload_json) VALUES(?,?,?)",
                (int(time.time() * 1000), kind, self._json(payload)),
            )

    def create_run(self, kind: str, payload: dict[str, Any] | None = None) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO runs(started_ts_ms, kind, status, payload_json) VALUES(?,?,?,?)",
                (int(time.time() * 1000), kind, "RUNNING", self._json(payload or {})),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE runs SET finished_ts_ms=?, status=?, payload_json=? WHERE id=?",
                (int(time.time() * 1000), status, self._json(payload), int(run_id)),
            )

    def _rows(self, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(query, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if "payload_json" in item:
                try:
                    item["payload"] = json.loads(item.pop("payload_json"))
                except json.JSONDecodeError:
                    item["payload"] = {}
            result.append(item)
        return result

    def recent_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM signals ORDER BY ts_ms DESC LIMIT ?", (max(1, limit),))

    def recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM trades ORDER BY closed_ts_ms DESC LIMIT ?", (max(1, limit),))

    def recent_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM decisions ORDER BY ts_ms DESC LIMIT ?", (max(1, limit),))

    def close(self) -> None:
        with self._lock:
            self._connection.close()
