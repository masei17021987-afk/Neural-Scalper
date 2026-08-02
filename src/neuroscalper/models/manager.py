from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ..domain import FeatureFrame, ModelPrediction
from ..paths import MODEL_DIR
from .network import RiskAwareLOBNet

logger = logging.getLogger(__name__)


class HeuristicPredictor:
    name = "microstructure_baseline"

    def predict(self, frame: FeatureFrame) -> ModelPrediction:
        f = frame.as_map()
        score = (
            0.22 * np.tanh(f.get("microprice_delta_bps", 0.0) / 1.5)
            + 0.24 * f.get("obi_10", 0.0)
            + 0.22 * f.get("trade_imbalance_20", 0.0)
            + 0.18 * np.tanh(f.get("return_10_bps", 0.0) / 5.0)
            + 0.14 * f.get("momentum_quality", 0.0)
        )
        score = float(np.clip(score, -0.98, 0.98))
        directional = abs(score)
        flat = max(0.04, 1.0 - directional)
        long_p = max(0.01, (1.0 + score) * directional / 2.0)
        short_p = max(0.01, (1.0 - score) * directional / 2.0)
        total = long_p + short_p + flat
        probabilities = {"SHORT": short_p / total, "FLAT": flat / total, "LONG": long_p / total}
        gross_edge = score * max(0.5, abs(f.get("return_3_bps", 0.0)) + abs(f.get("microprice_delta_bps", 0.0)) * 2.0)
        return ModelPrediction(
            probabilities=probabilities,
            expected_edge_bps=float(gross_edge),
            expected_volatility_bps=float(max(0.1, f.get("realized_vol_30_bps", 0.0))),
            model_name=self.name,
            model_ready=False,
        )


class ModelManager:
    def __init__(
        self,
        checkpoint: str = "",
        hidden_size: int = 96,
        dropout: float = 0.15,
        use_gpu: bool = True,
        *,
        autoload_default: bool = True,
    ) -> None:
        self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        self.hidden_size = hidden_size
        self.dropout = dropout
        self.model: RiskAwareLOBNet | None = None
        self.checkpoint_path: Path | None = None
        self.heuristic = HeuristicPredictor()
        self.metadata: dict[str, Any] = {}
        if checkpoint:
            self.load(checkpoint)
        elif autoload_default:
            default = MODEL_DIR / "best_model.pt"
            if default.exists():
                self.load(str(default))

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self, checkpoint: str) -> None:
        path = Path(checkpoint)
        if not path.is_absolute():
            path = MODEL_DIR / path
        payload = torch.load(path, map_location=self.device, weights_only=False)
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        hidden = int(metadata.get("hidden_size", self.hidden_size))
        dropout = float(metadata.get("dropout", self.dropout))
        model = RiskAwareLOBNet(hidden_size=hidden, dropout=dropout)
        state = payload.get("model_state", payload) if isinstance(payload, dict) else payload
        model.load_state_dict(state)
        model.to(self.device)
        model.eval()
        self.model = model
        self.checkpoint_path = path
        self.metadata = metadata
        logger.info("Loaded model %s on %s", path, self.device)

    def predict(self, frame: FeatureFrame) -> ModelPrediction:
        if self.model is None or not frame.lob_tensor:
            return self.heuristic.predict(frame)
        array = np.asarray(frame.lob_tensor, dtype=np.float32)
        tensor = torch.from_numpy(array).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            output = self.model(tensor)
            probabilities = torch.softmax(output.logits, dim=-1)[0].detach().cpu().tolist()
            edge = float(output.edge_bps[0].detach().cpu())
            volatility = float(output.volatility_bps[0].detach().cpu())
        return ModelPrediction(
            probabilities={"SHORT": probabilities[0], "FLAT": probabilities[1], "LONG": probabilities[2]},
            expected_edge_bps=edge,
            expected_volatility_bps=volatility,
            model_name=self.checkpoint_path.name if self.checkpoint_path else "RiskAwareLOBNet",
            model_ready=True,
        )

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "device": str(self.device),
            "checkpoint": str(self.checkpoint_path or ""),
            "metadata": self.metadata,
            "fallback": self.heuristic.name,
        }

    @staticmethod
    def save_checkpoint(path: Path, model: RiskAwareLOBNet, metadata: dict[str, Any], metrics: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_state": model.state_dict(),
            "metadata": metadata,
            "metrics": metrics,
        }
        torch.save(payload, path)
        path.with_suffix(".json").write_text(
            json.dumps({"metadata": metadata, "metrics": metrics}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
