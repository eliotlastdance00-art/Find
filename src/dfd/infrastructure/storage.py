"""Local filesystem storage for uploads and per-scan artifacts."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import BinaryIO

from dfd.domain import errors
from dfd.domain.ports import StoredFile

_SAFE_EXTENSION = re.compile(r"^\.[a-z0-9]{1,8}$")
_SAFE_ARTIFACT = re.compile(r"^[A-Za-z0-9_-]{1,64}\.(?:jpg|png|json|wav)$")
_CHUNK = 1 << 20


class LocalFileStorage:
    def __init__(self, uploads_dir: Path, scans_dir: Path) -> None:
        self._uploads = uploads_dir
        self._scans = scans_dir
        uploads_dir.mkdir(parents=True, exist_ok=True)
        scans_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self, scan_id: str, filename: str, stream: BinaryIO, max_bytes: int
    ) -> StoredFile:
        """Stream to disk under a server-chosen name while hashing and enforcing the size cap."""
        extension = Path(filename).suffix.lower()
        name = scan_id + (extension if _SAFE_EXTENSION.fullmatch(extension) else "")
        path = self._uploads / name
        digest, size = hashlib.sha256(), 0
        try:
            with path.open("wb") as target:
                while chunk := stream.read(_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise errors.FileTooLarge(limit_bytes=max_bytes)
                    digest.update(chunk)
                    target.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return StoredFile(name=name, path=path, size_bytes=size, sha256=digest.hexdigest())

    def upload_path(self, stored_name: str) -> Path:
        return self._uploads / Path(stored_name).name

    def scan_dir(self, scan_id: str) -> Path:
        path = self._scans / Path(scan_id).name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact(self, scan_id: str, name: str) -> Path | None:
        if not _SAFE_ARTIFACT.fullmatch(name):
            return None
        path = self._scans / Path(scan_id).name / name
        return path if path.is_file() else None

    def delete_scan(self, scan_id: str, stored_name: str) -> None:
        self.upload_path(stored_name).unlink(missing_ok=True)
        shutil.rmtree(self._scans / Path(scan_id).name, ignore_errors=True)
