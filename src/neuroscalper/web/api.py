from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import config_to_dict
from ..logging_setup import configure_logging
from ..paths import REPORT_DIR, STATIC_DIR
from ..runtime import NeuralScalperRuntime

configure_logging()


class ConfigPatch(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


class TrainingRequest(BaseModel):
    source: str = "synthetic"
    samples: int = Field(default=6000, ge=800, le=100000)


class BacktestRequest(BaseModel):
    source: str = "synthetic"
    steps: int = Field(default=6000, ge=500, le=2000000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = NeuralScalperRuntime()
    app.state.runtime = runtime
    yield
    await runtime.close()


app = FastAPI(
    title="CryptoHunter Neural Scalper",
    version="0.1.1",
    description="Локальная лаборатория нейросетевого скальпинга с paper-trading.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def runtime() -> NeuralScalperRuntime:
    instance = getattr(app.state, "runtime", None)
    if not instance:
        raise HTTPException(503, "Runtime ещё не готов")
    return instance


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    state = runtime().status(compact=True)
    return {"ok": True, "running": state["app"]["running"], "mode": state["app"]["mode"]}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return runtime().status()


@app.get("/api/history")
def history() -> dict[str, Any]:
    return runtime().history()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return config_to_dict(runtime().config)


@app.post("/api/config")
def set_config(request: ConfigPatch) -> dict[str, Any]:
    try:
        return {"ok": True, **runtime().apply_config(request.patch)}
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"Некорректная настройка: {exc}") from exc


@app.post("/api/actions/start-demo")
async def start_demo() -> dict[str, Any]:
    return await runtime().start_demo()


@app.post("/api/actions/start-market")
async def start_market() -> dict[str, Any]:
    return await runtime().start_public_market()


@app.post("/api/actions/stop")
async def stop() -> dict[str, Any]:
    return await runtime().stop()


@app.post("/api/actions/reset-paper")
def reset_paper() -> dict[str, Any]:
    return runtime().reset_paper()


@app.post("/api/actions/reset-kill-switch")
def reset_kill_switch() -> dict[str, Any]:
    return runtime().reset_kill_switch()


@app.post("/api/actions/train")
async def train(request: TrainingRequest) -> dict[str, Any]:
    return await runtime().start_training(request.source, request.samples)


@app.post("/api/actions/backtest")
async def backtest(request: BacktestRequest) -> dict[str, Any]:
    return await runtime().start_backtest(request.source, request.steps)


@app.get("/api/reports/latest-backtest")
def latest_backtest() -> dict[str, Any]:
    path = REPORT_DIR / "latest_backtest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(404, "Бэктест ещё не запускался") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Файл отчёта повреждён") from exc
