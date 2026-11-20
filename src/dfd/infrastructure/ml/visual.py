"""Face-forgery classifier: a timm backbone with one logit (positive = fake)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import timm
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from dfd.infrastructure.media.faces import Image
from dfd.infrastructure.ml.cards import ModelCard, load_card, verify_weights
from dfd.infrastructure.ml.gradcam import GradCAM, find_target_layer


def build_backbone(
    arch: str, pretrained: bool = False, drop_rate: float = 0.0, drop_path_rate: float = 0.0
) -> nn.Module:
    model: nn.Module = timm.create_model(
        arch,
        pretrained=pretrained,
        num_classes=1,
        drop_rate=drop_rate,
        drop_path_rate=drop_path_rate,
    )
    return model


def to_tensor(
    crops: Sequence[Image],
    size: int,
    mean: Sequence[float],
    std: Sequence[float],
) -> Tensor:
    """BGR uint8 crops -> normalised float tensor [N, 3, size, size]."""
    batch = np.empty((len(crops), size, size, 3), dtype=np.float32)
    for i, crop in enumerate(crops):
        if crop.shape[0] != size or crop.shape[1] != size:
            interpolation = cv2.INTER_AREA if crop.shape[0] > size else cv2.INTER_CUBIC
            crop = cv2.resize(crop, (size, size), interpolation=interpolation)  # noqa: PLW2901
        batch[i] = crop[..., ::-1]
    batch /= 255.0
    batch -= np.asarray(mean, dtype=np.float32)
    batch /= np.asarray(std, dtype=np.float32)
    return torch.from_numpy(batch.transpose(0, 3, 1, 2).copy())


def resolve_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def load_state(path: Path) -> dict[str, Tensor]:
    """Load a state dict saved by training (possibly half precision, possibly DataParallel)."""
    state = torch.load(path, map_location="cpu", weights_only=True)
    return {
        key.removeprefix("module."): value.float() if value.is_floating_point() else value
        for key, value in state.items()
    }


class VisualDetector:
    """Scores face crops and explains the score with Grad-CAM."""

    def __init__(self, model: nn.Module, card: ModelCard, device: torch.device) -> None:
        self.card = card
        self._device = device
        self._model = model.to(device).eval()
        self._target = find_target_layer(self._model, card.extra.get("cam_layer"))
        self._lock = threading.Lock()

    @classmethod
    def load(cls, model_dir: Path, device: str = "auto") -> VisualDetector:
        card = load_card(model_dir)
        weights = verify_weights(model_dir, card)
        model = build_backbone(card.arch)
        model.load_state_dict(load_state(weights), strict=True)
        return cls(model, card, resolve_device(device))

    def _batch(self, crops: Sequence[Image]) -> Tensor:
        card = self.card
        return to_tensor(crops, card.input_size, card.mean, card.std).to(self._device)

    def _probabilities(self, logits: Tensor) -> list[float]:
        scaled = logits.float() / self.card.temperature
        return [float(p) for p in torch.sigmoid(scaled).cpu()]

    def predict(self, crops: Sequence[Image], batch_size: int = 8) -> list[float]:
        """Calibrated probability of forgery for every crop."""
        probabilities: list[float] = []
        with self._lock, torch.inference_mode():
            for start in range(0, len(crops), batch_size):
                logits = self._model(self._batch(crops[start : start + batch_size]))
                probabilities.extend(self._probabilities(logits.reshape(-1)))
        return probabilities

    def explain(self, crop: Image) -> tuple[float, NDArray[np.float32]]:
        """Probability and a 0..1 heatmap (model input resolution) for one crop."""
        with self._lock, GradCAM(self._model, self._target) as cam:
            logits, maps = cam(self._batch([crop]))
        heatmap: NDArray[np.float32] = maps[0].float().cpu().numpy()
        return self._probabilities(logits)[0], heatmap
