"""Speech anti-spoofing detector built on AASIST (Jung et al., 2022)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn

from dfd.infrastructure.ml.cards import ModelCard, load_card, verify_weights
from dfd.infrastructure.ml.visual import resolve_device

SAMPLE_RATE = 16000
WINDOW = 64600  # ~4.04 s, the length AASIST is trained on

AASIST_CONFIG: dict[str, Any] = {
    "architecture": "AASIST",
    "nb_samp": WINDOW,
    "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
    "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5],
    "temperatures": [2.0, 2.0, 100.0, 100.0],
}


def build_aasist(config: dict[str, Any] | None = None) -> nn.Module:
    from dfd.infrastructure.ml.vendor.aasist_model import Model  # noqa: PLC0415

    model: nn.Module = Model(config or AASIST_CONFIG)
    return model


def spoof_logit(model: nn.Module, batch: torch.Tensor) -> torch.Tensor:
    """Log-odds of "spoof". AASIST returns (embedding, [spoof, bonafide] logits)."""
    _, output = model(batch)
    logits: torch.Tensor = output[:, 0] - output[:, 1]
    return logits


class AudioDetector:
    def __init__(self, model: nn.Module, card: ModelCard, device: torch.device) -> None:
        self.card = card
        self._device = device
        self._model = model.to(device).eval()
        self._lock = threading.Lock()

    @classmethod
    def load(cls, model_dir: Path, device: str = "auto") -> AudioDetector:
        card = load_card(model_dir)
        weights = verify_weights(model_dir, card)
        model = build_aasist(card.extra.get("model_config"))
        model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        return cls(model, card, resolve_device(device))

    def predict(self, batch: NDArray[np.float32], batch_size: int = 8) -> list[float]:
        """Calibrated probability that each ``[WINDOW]``-sample window is synthetic."""
        probabilities: list[float] = []
        with self._lock, torch.inference_mode():
            for start in range(0, len(batch), batch_size):
                chunk = torch.from_numpy(np.ascontiguousarray(batch[start : start + batch_size]))
                logits = spoof_logit(self._model, chunk.to(self._device))
                scaled = torch.sigmoid(logits.float() / self.card.temperature)
                probabilities.extend(float(p) for p in scaled.cpu())
        return probabilities
