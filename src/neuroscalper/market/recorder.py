from __future__ import annotations

import gzip
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain import BookSnapshot, FeatureFrame
from ..paths import DATA_DIR, ensure_runtime_dirs


class EventRecorder:
    """Append-only compressed recorder. A new file is opened every UTC hour."""

    def __init__(self, root: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.root = root or (DATA_DIR / "records")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._handles: dict[tuple[str, str, str], gzip.GzipFile] = {}

    @staticmethod
    def _hour_key(ts_ms: int) -> str:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y%m%d_%H")

    def _handle(self, symbol: str, kind: str, ts_ms: int) -> gzip.GzipFile:
        hour = self._hour_key(ts_ms)
        key = (symbol, kind, hour)
        handle = self._handles.get(key)
        if handle is not None:
            return handle
        symbol_dir = self.root / symbol.upper()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        path = symbol_dir / f"{kind}_{hour}.jsonl.gz"
        handle = gzip.open(path, "at", encoding="utf-8", compresslevel=5)
        self._handles[key] = handle
        self._close_old(symbol, kind, keep=key)
        return handle

    def _close_old(self, symbol: str, kind: str, keep: tuple[str, str, str]) -> None:
        for key, handle in list(self._handles.items()):
            if key[:2] == (symbol, kind) and key != keep:
                handle.close()
                self._handles.pop(key, None)

    def write_snapshot(self, snapshot: BookSnapshot) -> None:
        self._write(snapshot.symbol, "book", snapshot.local_ts_ms, snapshot.to_dict())

    def write_feature(self, frame: FeatureFrame) -> None:
        payload = {
            "symbol": frame.symbol,
            "exchange_ts_ms": frame.exchange_ts_ms,
            "local_ts_ms": frame.local_ts_ms,
            "names": frame.names,
            "values": frame.values,
            "regime": frame.regime,
            "metadata": frame.metadata,
        }
        self._write(frame.symbol, "features", frame.local_ts_ms, payload)

    def write_raw(self, symbol: str, kind: str, ts_ms: int, payload: dict[str, Any]) -> None:
        self._write(symbol, f"raw_{kind}", ts_ms, payload)

    def _write(self, symbol: str, kind: str, ts_ms: int, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock:
            handle = self._handle(symbol.upper(), kind, ts_ms)
            handle.write(line + "\n")
            handle.flush()

    def close(self) -> None:
        with self._lock:
            for handle in self._handles.values():
                handle.close()
            self._handles.clear()
