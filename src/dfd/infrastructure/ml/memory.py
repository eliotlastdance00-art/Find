"""Release temporary native allocations between large, sequential model operations.

PyTorch/ONNX free their tensors, but glibc may keep those blocks in the process.
On a small Linux host, returning unused pages prevents one model's temporary
workspace being retained while the other model runs. Other platforms just run GC.
This is not a memory cap: deployment still needs headroom for uploads and workers.
"""

from __future__ import annotations

import ctypes
import gc
import sys
from typing import Any


def _trim_function() -> Any:
    if sys.platform != "linux":
        return None
    try:
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        return trim
    except (AttributeError, OSError):  # musl and non-glibc hosts have no malloc_trim
        return None


_TRIM = _trim_function()


def release_unused_memory() -> None:
    gc.collect()
    if _TRIM is not None:
        _TRIM(0)
