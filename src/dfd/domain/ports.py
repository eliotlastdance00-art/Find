"""Interfaces the application layer depends on; infrastructure provides the implementations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from dfd.domain.entities import Analysis, MediaType, Role, Scan, ScanStatus, User, Verdict

ProgressCallback = Callable[[ScanStatus, float], None]


@dataclass(frozen=True, slots=True)
class StoredFile:
    name: str
    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class MediaInfo:
    media_type: MediaType
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool = False
    container: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
            "has_audio": self.has_audio,
            "container": self.container,
        }


@dataclass(frozen=True, slots=True)
class ScanFilter:
    verdict: Verdict | None = None
    media_type: MediaType | None = None
    query: str | None = None
    limit: int = 20
    offset: int = 0


class UserRepository(Protocol):
    def add(self, username: str, password_hash: str, role: Role) -> User: ...
    def get(self, user_id: int) -> User | None: ...
    def get_by_username(self, username: str) -> User | None: ...
    def count(self) -> int: ...


class ScanRepository(Protocol):
    def add(self, scan: Scan) -> None: ...
    def get(self, scan_id: str) -> Scan | None: ...
    def update(self, scan: Scan) -> None: ...
    def delete(self, scan_id: str) -> None: ...
    def search(self, user_id: int | None, criteria: ScanFilter) -> tuple[list[Scan], int]: ...
    def stats(self, user_id: int | None) -> dict[str, int]: ...
    def list_active(self) -> list[Scan]: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...


class TokenService(Protocol):
    def issue(self, user: User) -> str: ...
    def verify(self, token: str) -> int | None: ...
    def issue_media(self, user_id: int, scan_id: str) -> str: ...
    def verify_media(self, token: str, scan_id: str) -> int | None: ...


class FileStorage(Protocol):
    def save_upload(
        self, scan_id: str, filename: str, stream: BinaryIO, max_bytes: int
    ) -> StoredFile: ...
    def upload_path(self, stored_name: str) -> Path: ...
    def scan_dir(self, scan_id: str) -> Path: ...
    def artifact(self, scan_id: str, name: str) -> Path | None: ...
    def delete_scan(self, scan_id: str, stored_name: str) -> None: ...


class MediaInspector(Protocol):
    def inspect(self, path: Path) -> MediaInfo: ...


class MediaAnalyzer(Protocol):
    def analyze(
        self, path: Path, media_type: MediaType, workdir: Path, progress: ProgressCallback
    ) -> Analysis: ...


class JobQueue(Protocol):
    def enqueue(self, scan_id: str) -> None: ...


class EventPublisher(Protocol):
    def publish(self, scan_id: str, event: dict[str, Any]) -> None: ...


class ReportRenderer(Protocol):
    def render(self, scan: Scan, username: str, lang: str, artifacts: Path) -> bytes: ...


class AttemptLimiter(Protocol):
    def check(self, key: str) -> None: ...
    def failure(self, key: str) -> None: ...
    def reset(self, key: str) -> None: ...
