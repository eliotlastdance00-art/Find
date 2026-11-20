"""Face detection (YuNet via OpenCV) and square face cropping.

This module is shared by the training pipeline and the web application on purpose:
the detector must see faces cropped exactly the way it was trained on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]

YUNET_MODEL = Path(__file__).parent / "assets" / "face_detection_yunet_2023mar.onnx"
DEFAULT_MARGIN = 1.3


@dataclass(frozen=True, slots=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (round(self.x), round(self.y), round(self.w), round(self.h))


class FaceDetector:
    """Thread-safe wrapper around ``cv2.FaceDetectorYN``."""

    def __init__(
        self,
        model_path: Path = YUNET_MODEL,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        max_side: int = 640,
        min_face: int = 32,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"YuNet model not found: {model_path}")
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold, nms_threshold, 5000
        )
        self._max_side = max_side
        self._min_face = min_face
        self._lock = threading.Lock()

    def detect(self, image: Image) -> list[Face]:
        """Return faces in original image coordinates, largest first."""
        height, width = image.shape[:2]
        scale = min(1.0, self._max_side / max(height, width))
        resized = image
        if scale < 1.0:
            resized = cv2.resize(
                image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
            )
        with self._lock:
            self._detector.setInputSize((resized.shape[1], resized.shape[0]))
            _, raw = self._detector.detect(resized)
        if raw is None:
            return []
        faces = []
        for row in raw:
            x, y, w, h = (float(v) / scale for v in row[:4])
            if min(w, h) < self._min_face:
                continue
            faces.append(Face(x=x, y=y, w=w, h=h, score=float(row[14])))
        faces.sort(key=lambda f: f.area, reverse=True)
        return faces


def crop_face(
    image: Image, face: Face, margin: float = DEFAULT_MARGIN, size: int | None = None
) -> Image:
    """Square crop centred on the face, enlarged by ``margin``; edges are replicated."""
    height, width = image.shape[:2]
    side = max(2, round(max(face.w, face.h) * margin))
    x0 = round(face.x + face.w / 2 - side / 2)
    y0 = round(face.y + face.h / 2 - side / 2)
    x1, y1 = x0 + side, y0 + side
    pad = (max(0, -y0), max(0, y1 - height), max(0, -x0), max(0, x1 - width))
    crop = image[max(0, y0) : min(height, y1), max(0, x0) : min(width, x1)]
    if any(pad):
        crop = cv2.copyMakeBorder(crop, *pad, borderType=cv2.BORDER_REPLICATE)
    if size is not None and crop.shape[0] != size:
        interpolation = cv2.INTER_AREA if crop.shape[0] > size else cv2.INTER_CUBIC
        crop = cv2.resize(crop, (size, size), interpolation=interpolation)
    return np.ascontiguousarray(crop)
