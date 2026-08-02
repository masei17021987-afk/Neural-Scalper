from __future__ import annotations

import numpy as np

from neuroscalper.config import AppConfig
from neuroscalper.training.dataset import build_synthetic_dataset


def test_synthetic_dataset_has_all_classes_and_executable_labels():
    config = AppConfig()
    bundle = build_synthetic_dataset(config, samples=1800, seed=42)
    assert bundle.x.ndim == 4
    assert bundle.x.shape[-1] == 4
    assert set(np.unique(bundle.y)) == {0, 1, 2}
    assert bundle.metadata["labels"] == "executable_bid_ask_after_fees"
