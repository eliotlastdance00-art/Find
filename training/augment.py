"""Training-time augmentations for face crops, written with OpenCV/NumPy only.

They imitate what happens to media in the wild (re-compression, resizing, blur, noise,
colour shifts) so the detector cannot rely on one dataset's encoding fingerprint.
"""

from __future__ import annotations

import random

import cv2
import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]


def _jpeg(image: Image, rng: random.Random) -> Image:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(35, 95)])
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR) if ok else image


def _rescale(image: Image, rng: random.Random) -> Image:
    side = image.shape[0]
    small = max(32, int(side * rng.uniform(0.4, 0.8)))
    down = cv2.resize(image, (small, small), interpolation=cv2.INTER_AREA)
    mode = rng.choice([cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_NEAREST])
    return cv2.resize(down, (side, side), interpolation=mode)


def _colour(image: Image, rng: random.Random) -> Image:
    out = image.astype(np.float32) * rng.uniform(0.8, 1.2) + rng.uniform(-20, 20)
    return np.clip(out, 0, 255).astype(np.uint8)


def _hue_saturation(image: Image, rng: random.Random) -> Image:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + rng.randint(-8, 8)) % 180
    hsv[..., 1] = np.clip(hsv[..., 1] * rng.uniform(0.75, 1.25), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _noise(image: Image, rng: random.Random) -> Image:
    sigma = rng.uniform(2.0, 8.0)
    noise = np.random.default_rng(rng.getrandbits(32)).normal(0.0, sigma, image.shape)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _rotate(image: Image, rng: random.Random) -> Image:
    side = image.shape[0]
    matrix = cv2.getRotationMatrix2D((side / 2, side / 2), rng.uniform(-10, 10), 1.0)
    return cv2.warpAffine(image, matrix, (side, side), borderMode=cv2.BORDER_REFLECT_101)


def _erase(image: Image, rng: random.Random) -> Image:
    out = image.copy()
    side = image.shape[0]
    for _ in range(rng.randint(1, 2)):
        h, w = (int(side * rng.uniform(0.08, 0.25)) for _ in range(2))
        y, x = rng.randint(0, side - h), rng.randint(0, side - w)
        out[y : y + h, x : x + w] = rng.randint(0, 255)
    return out


def augment(image: Image, size: int, rng: random.Random) -> Image:
    """Return an augmented ``size`` x ``size`` BGR crop."""
    side = image.shape[0]
    crop = int(side * rng.uniform(0.82, 1.0))
    y, x = rng.randint(0, side - crop), rng.randint(0, side - crop)
    image = cv2.resize(
        image[y : y + crop, x : x + crop], (size, size), interpolation=cv2.INTER_AREA
    )
    if rng.random() < 0.5:
        image = image[:, ::-1].copy()
    if rng.random() < 0.3:
        image = _rotate(image, rng)
    if rng.random() < 0.5:
        image = _colour(image, rng)
    if rng.random() < 0.3:
        image = _hue_saturation(image, rng)
    if rng.random() < 0.25:
        image = _rescale(image, rng)
    if rng.random() < 0.2:
        kernel = rng.choice([3, 5])
        image = cv2.GaussianBlur(image, (kernel, kernel), 0)
    if rng.random() < 0.2:
        image = _noise(image, rng)
    if rng.random() < 0.5:
        image = _jpeg(image, rng)
    if rng.random() < 0.05:
        image = cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if rng.random() < 0.25:
        image = _erase(image, rng)
    return np.ascontiguousarray(image)
