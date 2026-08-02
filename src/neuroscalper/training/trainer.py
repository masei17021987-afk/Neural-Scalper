from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ..config import AppConfig
from ..models.manager import ModelManager
from ..models.network import RiskAwareLOBNet
from ..paths import DATA_DIR, MODEL_DIR
from .dataset import DatasetBundle, build_recorded_dataset, build_synthetic_dataset

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrainingResult:
    checkpoint: str
    samples: int
    train_loss: float
    validation_loss: float
    accuracy: float
    macro_f1: float
    device: str
    elapsed_seconds: float
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint,
            "samples": self.samples,
            "train_loss": self.train_loss,
            "validation_loss": self.validation_loss,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "device": self.device,
            "elapsed_seconds": self.elapsed_seconds,
            "metadata": self.metadata,
        }


def _split(bundle: DatasetBundle) -> tuple[TensorDataset, TensorDataset, TensorDataset]:
    n = len(bundle.x)
    train_end = max(1, int(n * 0.70))
    valid_end = max(train_end + 1, int(n * 0.85))

    def make(start: int, end: int) -> TensorDataset:
        return TensorDataset(
            torch.from_numpy(bundle.x[start:end]),
            torch.from_numpy(bundle.y[start:end]),
            torch.from_numpy(bundle.edge[start:end]),
            torch.from_numpy(bundle.volatility[start:end]),
        )

    return make(0, train_end), make(train_end, valid_end), make(valid_end, n)


def _loss(output, labels, edge, volatility) -> torch.Tensor:
    direction_loss = nn.functional.cross_entropy(output.logits, labels)
    edge_loss = nn.functional.smooth_l1_loss(output.edge_bps, edge)
    vol_loss = nn.functional.smooth_l1_loss(output.volatility_bps, volatility)
    return direction_loss + 0.20 * edge_loss + 0.08 * vol_loss


def _evaluate(model: RiskAwareLOBNet, loader: DataLoader, device: torch.device) -> tuple[float, float, float]:
    model.eval()
    losses: list[float] = []
    predictions: list[int] = []
    labels_all: list[int] = []
    with torch.inference_mode():
        for x, labels, edge, volatility in loader:
            x, labels = x.to(device), labels.to(device)
            edge, volatility = edge.to(device), volatility.to(device)
            output = model(x)
            losses.append(float(_loss(output, labels, edge, volatility).cpu()))
            predictions.extend(output.logits.argmax(dim=-1).cpu().tolist())
            labels_all.extend(labels.cpu().tolist())
    accuracy = accuracy_score(labels_all, predictions) if labels_all else 0.0
    macro_f1 = f1_score(labels_all, predictions, average="macro", zero_division=0) if labels_all else 0.0
    return float(np.mean(losses) if losses else math.inf), float(accuracy), float(macro_f1)


def train_model(
    config: AppConfig,
    source: str = "synthetic",
    synthetic_samples: int = 6000,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> TrainingResult:
    started = time.time()
    if progress:
        progress({"stage": "dataset", "progress": 0.03, "message": "Подготовка временных последовательностей"})
    if source == "recorded":
        bundle = build_recorded_dataset(config, DATA_DIR / "records")
    else:
        bundle = build_synthetic_dataset(config, samples=synthetic_samples)
    train_set, valid_set, test_set = _split(bundle)
    device = torch.device("cuda" if config.model.use_gpu and torch.cuda.is_available() else "cpu")
    model = RiskAwareLOBNet(config.model.hidden_size, config.model.dropout).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.model.learning_rate, weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda" and config.model.mixed_precision)
    train_loader = DataLoader(train_set, batch_size=config.model.batch_size, shuffle=True, drop_last=False)
    valid_loader = DataLoader(valid_set, batch_size=config.model.batch_size, shuffle=False)
    test_loader = DataLoader(test_set, batch_size=config.model.batch_size, shuffle=False)
    best_state = None
    best_val = math.inf
    last_train_loss = math.inf

    for epoch in range(config.model.epochs):
        model.train()
        losses: list[float] = []
        for x, labels, edge, volatility in train_loader:
            x, labels = x.to(device), labels.to(device)
            edge, volatility = edge.to(device), volatility.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda" and config.model.mixed_precision):
                output = model(x)
                loss = _loss(output, labels, edge, volatility)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        last_train_loss = float(np.mean(losses) if losses else math.inf)
        val_loss, val_accuracy, val_f1 = _evaluate(model, valid_loader, device)
        if val_loss < best_val:
            best_val = val_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        if progress:
            progress({
                "stage": "training",
                "epoch": epoch + 1,
                "epochs": config.model.epochs,
                "progress": 0.10 + 0.78 * (epoch + 1) / config.model.epochs,
                "message": f"Эпоха {epoch + 1}/{config.model.epochs}",
                "train_loss": last_train_loss,
                "validation_loss": val_loss,
                "validation_accuracy": val_accuracy,
                "validation_f1": val_f1,
            })
    if best_state is not None:
        model.load_state_dict(best_state)
    test_loss, accuracy, macro_f1 = _evaluate(model, test_loader, device)
    metadata = {
        **bundle.metadata,
        "hidden_size": config.model.hidden_size,
        "dropout": config.model.dropout,
        "sequence_length": config.model.sequence_length,
        "levels": config.market.depth_levels,
        "classes": ["SHORT", "FLAT", "LONG"],
        "trained_at": int(time.time()),
    }
    metrics = {
        "train_loss": last_train_loss,
        "validation_loss": best_val,
        "test_loss": test_loss,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
    }
    checkpoint = MODEL_DIR / f"lob_scalper_{int(time.time())}.pt"
    ModelManager.save_checkpoint(checkpoint, model, metadata, metrics)
    best = MODEL_DIR / "best_model.pt"
    ModelManager.save_checkpoint(best, model, metadata, metrics)
    elapsed = time.time() - started
    result = TrainingResult(
        checkpoint=str(checkpoint),
        samples=len(bundle.x),
        train_loss=last_train_loss,
        validation_loss=best_val,
        accuracy=accuracy,
        macro_f1=macro_f1,
        device=str(device),
        elapsed_seconds=elapsed,
        metadata=metadata,
    )
    if progress:
        progress({"stage": "complete", "progress": 1.0, "message": "Модель сохранена", **result.to_dict()})
    logger.info("Training complete: %s", result.to_dict())
    return result
