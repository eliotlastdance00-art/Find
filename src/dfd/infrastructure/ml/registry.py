"""Lazy, thread-safe access to the detectors stored under the weights directory.

Layout::

    weights/
      visual/  model_card.json + weights file
      audio/   model_card.json + weights file
      synthetic/ model_card.json + downloaded model.onnx
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from dfd.domain import errors
from dfd.infrastructure.ml.audio import AudioDetector
from dfd.infrastructure.ml.cards import CARD_FILE, load_card
from dfd.infrastructure.ml.smaug import SmaugDetector
from dfd.infrastructure.ml.visual import VisualDetector

log = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, weights_dir: Path, device: str = "auto") -> None:
        self._dir = weights_dir
        self._device = device
        self._visual: VisualDetector | None = None
        self._audio: AudioDetector | None = None
        self._synthetic: SmaugDetector | None = None
        self._lock = threading.Lock()

    def _available(self, kind: str) -> bool:
        return (self._dir / kind / CARD_FILE).is_file()

    def visual(self) -> VisualDetector:
        with self._lock:
            if self._visual is None:
                if not self._available("visual"):
                    raise errors.ModelUnavailable(kind="visual")
                self._visual = VisualDetector.load(self._dir / "visual", self._device)
                log.info("loaded visual model %s", self._visual.card.label)
            return self._visual

    def audio(self) -> AudioDetector:
        with self._lock:
            if self._audio is None:
                if not self._available("audio"):
                    raise errors.ModelUnavailable(kind="audio")
                self._audio = AudioDetector.load(self._dir / "audio", self._device)
                log.info("loaded audio model %s", self._audio.card.label)
            return self._audio

    def synthetic(self) -> SmaugDetector:
        with self._lock:
            if self._synthetic is None:
                if not self._available("synthetic"):
                    raise errors.ModelUnavailable(kind="synthetic")
                self._synthetic = SmaugDetector.load(self._dir / "synthetic")
                log.info("loaded AI-image model %s", self._synthetic.card.label)
            return self._synthetic

    def preload(self) -> None:
        for kind, loader in (
            ("visual", self.visual),
            ("audio", self.audio),
            ("synthetic", self.synthetic),
        ):
            try:
                loader()
            except errors.ModelUnavailable:
                log.warning("%s model is not installed in %s", kind, self._dir)

    def status(self) -> dict[str, dict[str, Any]]:
        """Describe installed models from their cards, without loading any weights."""
        report: dict[str, dict[str, Any]] = {}
        for kind in ("visual", "audio", "synthetic"):
            if not self._available(kind):
                report[kind] = {"available": False}
                continue
            try:
                card = load_card(self._dir / kind)
            except (OSError, ValueError, KeyError) as error:
                report[kind] = {"available": False, "error": str(error)}
                continue
            report[kind] = {
                "available": (self._dir / kind / card.weights_file).is_file(),
                "name": card.name,
                "version": card.version,
                "arch": card.arch,
                "provisional": card.provisional,
                "trained_on": card.trained_on,
                "metrics": card.metrics,
            }
        return report
