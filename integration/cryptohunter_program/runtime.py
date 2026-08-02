"""Reference process adapter. Do not mount without tenant/process isolation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


class NeuralScalperProcessAdapter:
    def __init__(self, root: str | Path, port: int) -> None:
        self.root = Path(root).resolve()
        self.port = int(port)
        self.process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, var_dir: str | Path) -> None:
        if self.process and self.process.poll() is None:
            return
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": str(self.root / "src"),
            "NEUROSCALPER_HOST": "127.0.0.1",
            "NEUROSCALPER_PORT": str(self.port),
            "NEUROSCALPER_VAR_DIR": str(Path(var_dir).resolve()),
        })
        self.process = subprocess.Popen(
            [sys.executable, "-m", "neuroscalper.launcher"],
            cwd=self.root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def status(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/status", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {"state": "ERROR", "error": str(exc), "live_execution": False}
        return {
            "state": "RUNNING" if payload.get("app", {}).get("running") else "IDLE",
            "paper": payload.get("paper", {}),
            "risk": payload.get("risk", {}),
            "market": payload.get("market", {}),
            "live_execution": False,
        }
