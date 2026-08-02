from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAR_DIR = Path(os.getenv("NEUROSCALPER_VAR_DIR", PROJECT_ROOT / "var")).resolve()
DATA_DIR = VAR_DIR / "data"
LOG_DIR = VAR_DIR / "logs"
MODEL_DIR = VAR_DIR / "models"
REPORT_DIR = VAR_DIR / "reports"
CACHE_DIR = VAR_DIR / "cache"
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def ensure_runtime_dirs() -> None:
    for path in (VAR_DIR, DATA_DIR, LOG_DIR, MODEL_DIR, REPORT_DIR, CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)
