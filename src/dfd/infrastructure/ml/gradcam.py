"""Grad-CAM (Selvaraju et al., 2017) for single-logit classifiers, plus heatmap rendering."""

from __future__ import annotations

from types import TracebackType

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from numpy.typing import NDArray
from torch import Tensor, nn

from dfd.infrastructure.media.faces import Image


def find_target_layer(model: nn.Module, name: str | None = None) -> nn.Module:
    """Resolve the layer whose activations feed global pooling.

    ``name`` is a dotted attribute path. Without it, timm's ``bn2`` / ``conv_head`` are tried
    (EfficientNet family), then the last convolution in the network.
    """
    if name:
        module: nn.Module = model
        for part in name.split("."):
            module = module[int(part)] if part.isdigit() else getattr(module, part)  # type: ignore[index]
        return module
    for candidate in ("bn2", "conv_head"):
        layer = getattr(model, candidate, None)
        if isinstance(layer, nn.Module) and not isinstance(layer, nn.Identity):
            return layer
    convs = [m for m in model.modules() if isinstance(m, nn.Conv2d)]
    if not convs:
        raise ValueError("model has no convolutional layer for Grad-CAM")
    return convs[-1]


class GradCAM:
    """Context manager that hooks ``layer`` and turns gradients of the logit into heatmaps."""

    def __init__(self, model: nn.Module, layer: nn.Module) -> None:
        self._model = model
        self._activations: Tensor | None = None
        self._gradients: Tensor | None = None
        self._handle = layer.register_forward_hook(self._capture)

    def _capture(self, _module: nn.Module, _inputs: object, output: Tensor) -> None:
        self._activations = output
        if output.requires_grad:
            output.register_hook(self._store_gradient)  # type: ignore[no-untyped-call]

    def _store_gradient(self, gradient: Tensor) -> None:
        self._gradients = gradient

    def __enter__(self) -> GradCAM:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._handle.remove()
        self._activations = self._gradients = None

    def __call__(self, batch: Tensor) -> tuple[Tensor, Tensor]:
        """Return (logits [N], cams [N, H, W] in 0..1 at the input resolution).

        The map explains the "fake" logit: bright regions pushed the score towards fake.
        """
        self._activations = self._gradients = None
        with torch.enable_grad():
            batch = batch.detach().clone().requires_grad_(True)
            logits = self._model(batch).reshape(batch.shape[0], -1)[:, 0]
            self._model.zero_grad(set_to_none=True)
            logits.sum().backward()
        if self._activations is None or self._gradients is None:
            raise RuntimeError("Grad-CAM hooks captured nothing; wrong target layer?")
        activations, gradients = self._activations.detach(), self._gradients.detach()
        weights = gradients.mean(dim=(2, 3), keepdim=True)
        cams = F.relu((weights * activations).sum(dim=1, keepdim=True))
        cams = F.interpolate(cams, size=batch.shape[-2:], mode="bilinear", align_corners=False)
        cams = cams[:, 0]
        flat = cams.flatten(1)
        low = flat.min(dim=1).values[:, None, None]
        high = flat.max(dim=1).values[:, None, None]
        cams = (cams - low) / (high - low).clamp_min(1e-8)
        return logits.detach(), cams


def overlay_heatmap(image: Image, cam: NDArray[np.float32], alpha: float = 0.55) -> Image:
    """Blend a 0..1 heatmap over a BGR image; cold regions stay untouched."""
    height, width = image.shape[:2]
    cam = np.clip(cv2.resize(cam.astype(np.float32), (width, height)), 0.0, 1.0)
    colour = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET).astype(np.float32)
    weight = (alpha * cam)[..., None]
    blended = image.astype(np.float32) * (1.0 - weight) + colour * weight
    result: NDArray[np.uint8] = np.clip(blended, 0, 255).astype(np.uint8)
    return result
