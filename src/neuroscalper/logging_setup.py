from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from threading import RLock
from typing import Any

from .paths import LOG_DIR, ensure_runtime_dirs


class MemoryLogHandler(logging.Handler):
    def __init__(self, max_entries: int = 1000) -> None:
        super().__init__()
        self.entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self.lock = RLock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            with self.lock:
                self.entries.append(entry)
        except Exception:
            self.handleError(record)

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.entries)[-max(1, limit):]


memory_handler = MemoryLogHandler()


def configure_logging() -> None:
    ensure_runtime_dirs()
    root = logging.getLogger()
    if getattr(root, "_neuroscalper_configured", False):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = RotatingFileHandler(
        LOG_DIR / "neuroscalper.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    memory_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(memory_handler)
    setattr(root, "_neuroscalper_configured", True)
