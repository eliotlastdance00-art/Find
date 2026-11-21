"""Model cards: the JSON file that travels with every set of weights."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dfd.domain.entities import Thresholds, Verdict

CARD_FILE = "model_card.json"

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True, slots=True)
class ModelCard:
    name: str
    version: str
    kind: str  # "visual" | "audio"
    arch: str
    weights_file: str
    sha256: str
    thresholds: dict[str, Thresholds]
    temperature: float = 1.0
    input_size: int = 0
    mean: tuple[float, float, float] = IMAGENET_MEAN
    std: tuple[float, float, float] = IMAGENET_STD
    provisional: bool = False
    trained_on: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    # Strongest verdict this model may give on its own; None means no limit. Set while a model
    # is known to be unreliable on part of its expected input (see docs: Turkmen speech).
    max_verdict: Verdict | None = None

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"

    def thresholds_for(self, scope: str) -> Thresholds:
        return self.thresholds.get(scope) or next(iter(self.thresholds.values()))

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "arch": self.arch,
            "weights_file": self.weights_file,
            "sha256": self.sha256,
            "temperature": self.temperature,
            "input_size": self.input_size,
            "mean": list(self.mean),
            "std": list(self.std),
            "provisional": self.provisional,
            "trained_on": self.trained_on,
            "thresholds": {
                scope: {"real_max": t.real_max, "fake_min": t.fake_min}
                for scope, t in self.thresholds.items()
            },
            "metrics": self.metrics,
            "extra": self.extra,
            **({"max_verdict": self.max_verdict.value} if self.max_verdict else {}),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ModelCard:
        thresholds = {
            scope: Thresholds(float(t["real_max"]), float(t["fake_min"]))
            for scope, t in data["thresholds"].items()
        }
        if not thresholds:
            raise ValueError("model card has no thresholds")
        mean = tuple(float(v) for v in data.get("mean", IMAGENET_MEAN))
        std = tuple(float(v) for v in data.get("std", IMAGENET_STD))
        limit = data.get("max_verdict")
        if limit is not None and limit not in (Verdict.REAL.value, Verdict.SUSPICIOUS.value):
            raise ValueError(f"model card has an unsupported max_verdict: {limit!r}")
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            kind=str(data["kind"]),
            arch=str(data["arch"]),
            weights_file=str(data["weights_file"]),
            sha256=str(data.get("sha256", "")),
            thresholds=thresholds,
            temperature=float(data.get("temperature", 1.0)),
            input_size=int(data.get("input_size", 0)),
            mean=(mean[0], mean[1], mean[2]),
            std=(std[0], std[1], std[2]),
            provisional=bool(data.get("provisional", False)),
            trained_on=str(data.get("trained_on", "")),
            metrics=dict(data.get("metrics", {})),
            extra=dict(data.get("extra", {})),
            max_verdict=Verdict(limit) if limit is not None else None,
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_card(model_dir: Path) -> ModelCard:
    return ModelCard.from_json(json.loads((model_dir / CARD_FILE).read_text(encoding="utf-8")))


def save_card(model_dir: Path, card: ModelCard) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / CARD_FILE).write_text(
        json.dumps(card.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def verify_weights(model_dir: Path, card: ModelCard) -> Path:
    """Return the weights path after checking it exists and matches the recorded hash."""
    path = model_dir / card.weights_file
    if not path.is_file():
        raise FileNotFoundError(f"weights file missing: {path}")
    if card.sha256 and file_sha256(path) != card.sha256:
        raise ValueError(f"weights checksum mismatch for {path.name}")
    return path
