"""Request and response models of the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from dfd.domain.entities import Scan, User


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    @classmethod
    def of(cls, user: User) -> UserOut:
        return cls(id=user.id, username=user.username, role=user.role.value)


class SessionOut(BaseModel):
    user: UserOut
    token: str
    expires_in: int


class ScanSummary(BaseModel):
    id: str
    filename: str
    media_type: str
    status: str
    progress: float
    verdict: str | None
    prob_fake: float | None
    visual_prob: float | None
    audio_prob: float | None
    size_bytes: int
    error: str | None
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def of(cls, scan: Scan) -> ScanSummary:
        return cls(**_summary(scan))


class ScanOut(ScanSummary):
    sha256: str
    details: dict[str, Any]
    media_token: str

    @classmethod
    def build(cls, scan: Scan, media_token: str) -> ScanOut:
        return cls(
            **_summary(scan), sha256=scan.sha256, details=scan.details, media_token=media_token
        )


class HistoryOut(BaseModel):
    items: list[ScanSummary]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    params: dict[str, Any] = {}


class ErrorOut(BaseModel):
    error: ErrorBody


def _summary(scan: Scan) -> dict[str, Any]:
    return {
        "id": scan.id,
        "filename": scan.filename,
        "media_type": scan.media_type.value,
        "status": scan.status.value,
        "progress": scan.progress,
        "verdict": scan.verdict.value if scan.verdict else None,
        "prob_fake": scan.prob_fake,
        "visual_prob": scan.visual_prob,
        "audio_prob": scan.audio_prob,
        "size_bytes": scan.size_bytes,
        "error": scan.error,
        "duration_ms": scan.duration_ms,
        "created_at": scan.created_at,
        "finished_at": scan.finished_at,
    }
