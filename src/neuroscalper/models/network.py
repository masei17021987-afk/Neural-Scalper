from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(slots=True)
class NetworkOutput:
    logits: torch.Tensor
    edge_bps: torch.Tensor
    volatility_bps: torch.Tensor
    embedding: torch.Tensor


class ResidualConvBlock(nn.Module):
    def __init__(self, channels: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=(3, 3), padding=1),
            nn.BatchNorm2d(channels),
            nn.SiLU(),
            nn.Dropout2d(dropout),
            nn.Conv2d(channels, channels, kernel_size=(3, 3), padding=1),
            nn.BatchNorm2d(channels),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.silu(x + self.net(x))


class RiskAwareLOBNet(nn.Module):
    """Compact LOB encoder with direction, executable-edge and risk heads.

    Input shape: [batch, time, levels, 4]
    Channels: relative bid price, log bid size, relative ask price, log ask size.
    """

    def __init__(self, hidden_size: int = 96, dropout: float = 0.15) -> None:
        super().__init__()
        channels = max(32, hidden_size // 2)
        self.stem = nn.Sequential(
            nn.Conv2d(4, channels, kernel_size=(5, 3), padding=(2, 1)),
            nn.BatchNorm2d(channels),
            nn.SiLU(),
        )
        self.residual = nn.Sequential(
            ResidualConvBlock(channels, dropout),
            ResidualConvBlock(channels, dropout),
        )
        self.temporal = nn.GRU(
            input_size=channels,
            hidden_size=hidden_size,
            num_layers=2,
            batch_first=True,
            dropout=dropout,
            bidirectional=False,
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1),
        )
        self.shared = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, hidden_size),
            nn.SiLU(),
            nn.Dropout(dropout),
        )
        self.direction_head = nn.Linear(hidden_size, 3)
        self.edge_head = nn.Linear(hidden_size, 1)
        self.volatility_head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> NetworkOutput:
        if x.ndim != 4 or x.shape[-1] != 4:
            raise ValueError(f"Expected [B,T,L,4], received {tuple(x.shape)}")
        x = x.permute(0, 3, 1, 2).contiguous()
        x = self.residual(self.stem(x))
        x = x.mean(dim=-1).transpose(1, 2).contiguous()
        sequence, _ = self.temporal(x)
        weights = torch.softmax(self.attention(sequence).squeeze(-1), dim=-1)
        embedding = torch.sum(sequence * weights.unsqueeze(-1), dim=1)
        embedding = self.shared(embedding)
        logits = self.direction_head(embedding)
        edge_bps = torch.tanh(self.edge_head(embedding).squeeze(-1)) * 60.0
        volatility_bps = F.softplus(self.volatility_head(embedding).squeeze(-1)) * 10.0
        return NetworkOutput(logits, edge_bps, volatility_bps, embedding)

    def export_metadata(self) -> dict[str, Any]:
        return {
            "name": self.__class__.__name__,
            "classes": ["SHORT", "FLAT", "LONG"],
            "input": "[batch,time,levels,4]",
            "heads": ["direction", "executable_edge_bps", "volatility_bps"],
        }
