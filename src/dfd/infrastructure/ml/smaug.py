"""Smaug's quantised, image-only ONNX adapter (CPU, no remote code).

Preprocessing follows Abacus.AI's ``smaug_image_detect.views``: three 528 px
views at native resolution, resized only outside the 528..576 short-side band.
See docs/SMAUG.md for pinned sources, licence and the uncalibrated decision rule.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image as PillowImage

from dfd.domain import errors
from dfd.infrastructure.media.faces import Image
from dfd.infrastructure.ml.cards import ModelCard, load_card, verify_weights
from dfd.infrastructure.ml.memory import release_unused_memory

log = logging.getLogger(__name__)
CROP = 528
SIDE = 576


def image_views(image: Image) -> Iterator[NDArray[np.float32]]:
    """Already EXIF-oriented BGR uint8 -> three RGB [1,3,528,528] float32 views.

    The decoder shared with the face path honours EXIF orientation. There is no
    ImageNet normalisation. Yielding one view at a time bounds inference memory.
    """
    picture = PillowImage.fromarray(image[..., ::-1])
    width, height = picture.size
    short = min(width, height)
    if short > SIDE:
        scale = SIDE / short
        picture = picture.resize(
            (round(width * scale), round(height * scale)), PillowImage.Resampling.LANCZOS
        )
    elif short < CROP:
        scale = CROP / short
        picture = picture.resize(
            (math.ceil(width * scale), math.ceil(height * scale)), PillowImage.Resampling.BICUBIC
        )
    width, height = picture.size
    cx, cy = (width - CROP) // 2, (height - CROP) // 2
    spots = (
        ((0, cy), (cx, cy), (width - CROP, cy))
        if width >= height
        else ((cx, 0), (cx, cy), (cx, height - CROP))
    )
    for left, top in spots:
        view = picture.crop((left, top, left + CROP, top + CROP))
        pixels = np.asarray(view, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        yield np.ascontiguousarray(pixels)


def sigmoid(logit: float) -> float:
    """Overflow-safe sigmoid; reject invalid inference rather than silently say real."""
    if not math.isfinite(logit):
        raise ValueError("Smaug returned a non-finite logit")
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    value = math.exp(logit)
    return value / (1.0 + value)


class SmaugDetector:
    def __init__(self, session: Any, card: ModelCard) -> None:
        self.card = card
        self._session = session
        self._input = session.get_inputs()[0].name
        self._lock = threading.Lock()

    @classmethod
    def load(cls, model_dir: Path) -> SmaugDetector:
        import onnxruntime as ort  # noqa: PLC0415

        try:
            card = load_card(model_dir)
            weights = verify_weights(model_dir, card)
            options = ort.SessionOptions()
            # This graph is already optimised. Re-optimising costs time and memory.
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            # Avoid keeping a second, prepacked copy of the quantised weights.
            options.add_session_config_entry("session.disable_prepacking", "1")
            session = ort.InferenceSession(
                str(weights), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as error:
            log.warning("could not load Smaug: %s", error)
            raise errors.ModelUnavailable(kind="synthetic") from error
        return cls(session, card)

    def predict(self, image: Image) -> float:
        """Mean of crop logits THEN sigmoid, never the mean of probabilities."""
        logits: list[float] = []
        with self._lock:
            release_unused_memory()
            for pixels in image_views(image):
                output = np.asarray(self._session.run(None, {self._input: pixels})[0])
                if output.size != 1:
                    raise ValueError("Smaug must return one logit per view")
                logits.append(float(output.reshape(-1)[0]))
                release_unused_memory()
        return sigmoid(sum(logits) / len(logits))
