"""Evenly spaced frame sampling from a video file."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from dfd.infrastructure.media.faces import Image


@dataclass(frozen=True, slots=True)
class Frame:
    index: int
    timestamp_s: float
    image: Image


def pick_indices(total: int, count: int) -> list[int]:
    """``count`` indices spread evenly over ``range(total)``, centred in their bins."""
    if total <= 0 or count <= 0:
        return []
    if count >= total:
        return list(range(total))
    step = total / count
    return sorted({min(total - 1, int(step * i + step / 2)) for i in range(count)})


def sample_frames(path: Path, count: int) -> Iterator[Frame]:
    """Yield about ``count`` frames by decoding sequentially (seeking is unreliable)."""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        fps = fps if 1.0 <= fps <= 240.0 else 25.0
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 0:
            wanted = set(pick_indices(total, count))
            last = max(wanted)
            index = 0
            while index <= last and capture.grab():
                if index in wanted:
                    ok, image = capture.retrieve()
                    if ok and image is not None:
                        yield Frame(index, index / fps, image)
                index += 1
            return
        # Containers without a frame count: keep every frame in memory-light reservoir steps.
        buffered: list[Frame] = []
        index = 0
        stride = 1
        while True:
            ok, image = capture.read()
            if not ok or image is None:
                break
            if index % stride == 0:
                buffered.append(Frame(index, index / fps, image))
                if len(buffered) >= 2 * count:
                    buffered = buffered[::2]
                    stride *= 2
            index += 1
        keep = pick_indices(len(buffered), count)
        for i in keep:
            yield buffered[i]
    finally:
        capture.release()


def read_image(path: Path) -> Image | None:
    """Decode a still image as BGR; honours EXIF orientation, handles non-ASCII paths."""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return image if image is not None and image.size else None
