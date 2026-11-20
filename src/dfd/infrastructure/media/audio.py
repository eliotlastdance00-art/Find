"""PCM helpers: WAV reading and fixed-size windowing for the anti-spoofing model."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

Samples = NDArray[np.float32]
SILENCE_RMS = 1e-3


def read_wav(path: Path) -> tuple[Samples, int]:
    """Read a 16-bit PCM WAV as mono float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("expected 16-bit PCM")
        rate, channels = handle.getframerate(), handle.getnchannels()
        raw = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    samples = raw.astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def is_silent(samples: Samples) -> bool:
    return samples.size == 0 or float(np.sqrt(np.mean(np.square(samples)))) < SILENCE_RMS


def windows(
    samples: Samples, sample_rate: int, size: int, hop: int
) -> tuple[Samples, list[tuple[float, float]]]:
    """Cut ``samples`` into windows of ``size``.

    A clip shorter than one window is repeated to fill it (the convention the model was
    trained with). The last window is right-aligned so no audio is dropped.
    """
    if samples.size == 0:
        raise ValueError("no audio samples")
    total = samples.size
    if total <= size:
        repeats = int(np.ceil(size / total))
        return np.tile(samples, repeats)[:size][None, :], [(0.0, total / sample_rate)]
    starts = list(range(0, total - size + 1, hop))
    if starts[-1] != total - size:
        starts.append(total - size)
    batch = np.stack([samples[s : s + size] for s in starts])
    spans = [(s / sample_rate, (s + size) / sample_rate) for s in starts]
    return batch, spans
