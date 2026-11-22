"""Core business entities. This module depends on nothing but the standard library."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ScanStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    ANALYZING = "analyzing"
    EXPLAINING = "explaining"
    DONE = "done"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (ScanStatus.DONE, ScanStatus.FAILED)

    @property
    def is_active(self) -> bool:
        return self in (
            ScanStatus.QUEUED,
            ScanStatus.PREPROCESSING,
            ScanStatus.ANALYZING,
            ScanStatus.EXPLAINING,
        )


class Verdict(StrEnum):
    REAL = "real"
    SUSPICIOUS = "suspicious"
    FAKE = "fake"
    INCONCLUSIVE = "inconclusive"


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


@dataclass(slots=True)
class User:
    id: int
    username: str
    password_hash: str
    role: Role
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Decision band for one modality: p <= real_max is real, p >= fake_min is fake."""

    real_max: float
    fake_min: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.real_max <= self.fake_min <= 1.0:
            raise ValueError(f"invalid thresholds: {self.real_max=} {self.fake_min=}")


@dataclass(frozen=True, slots=True)
class FrameFinding:
    """One analysed face: a video frame, or one face of a still image."""

    index: int
    timestamp_s: float | None
    prob_fake: float
    box: tuple[int, int, int, int] | None = None
    face_file: str | None = None
    heatmap_file: str | None = None


@dataclass(frozen=True, slots=True)
class SegmentFinding:
    """One analysed audio window."""

    start_s: float
    end_s: float
    prob_fake: float


@dataclass(frozen=True, slots=True)
class ModalityResult:
    prob_fake: float
    thresholds: Thresholds
    model: str
    provisional: bool = False
    max_verdict: Verdict | None = None  # the model's card forbids anything stronger


@dataclass(slots=True)
class Analysis:
    """Raw output of the analysis pipeline, before a verdict is derived."""

    visual: ModalityResult | None = None
    audio: ModalityResult | None = None
    synthetic: ModalityResult | None = None
    provenance: list[str] = field(default_factory=list)
    frames: list[FrameFinding] = field(default_factory=list)
    segments: list[SegmentFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    overview_file: str | None = None
    media_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Scan:
    id: str
    user_id: int
    filename: str
    stored_name: str
    sha256: str
    size_bytes: int
    media_type: MediaType
    status: ScanStatus
    created_at: datetime
    progress: float = 0.0
    verdict: Verdict | None = None
    prob_fake: float | None = None
    visual_prob: float | None = None
    audio_prob: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int | None = None
    finished_at: datetime | None = None
