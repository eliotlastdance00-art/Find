"""Scan use cases: upload, start, read, list, delete, and the processing job itself."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from dfd.domain import errors
from dfd.domain.entities import (
    Analysis,
    MediaType,
    ModalityResult,
    Role,
    Scan,
    ScanStatus,
    User,
    Verdict,
)
from dfd.domain.ports import (
    EventPublisher,
    FileStorage,
    JobQueue,
    MediaAnalyzer,
    MediaInspector,
    ScanFilter,
    ScanRepository,
)
from dfd.domain.scoring import cap, classify, fuse, headline_probability

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class ScanService:
    def __init__(
        self,
        scans: ScanRepository,
        storage: FileStorage,
        inspector: MediaInspector,
        queue: JobQueue,
        max_upload_bytes: int,
        max_duration_s: float,
    ) -> None:
        self._scans = scans
        self._storage = storage
        self._inspector = inspector
        self._queue = queue
        self._max_upload_bytes = max_upload_bytes
        self._max_duration_s = max_duration_s

    def upload(self, user: User, filename: str, stream: BinaryIO) -> Scan:
        """Store a file, verify it really is supported media and register it for scanning."""
        scan_id = uuid.uuid4().hex
        stored = self._storage.save_upload(scan_id, filename, stream, self._max_upload_bytes)
        try:
            if stored.size_bytes == 0:
                raise errors.EmptyFile()
            info = self._inspector.inspect(stored.path)
            if info.duration_s is not None and info.duration_s > self._max_duration_s:
                raise errors.MediaTooLong(limit_s=self._max_duration_s)
        except Exception:
            self._storage.delete_scan(scan_id, stored.name)
            raise
        scan = Scan(
            id=scan_id,
            user_id=user.id,
            filename=Path(filename).name[:255] or "file",
            stored_name=stored.name,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            media_type=info.media_type,
            status=ScanStatus.UPLOADED,
            created_at=_now(),
            details={"media": info.as_dict()},
        )
        self._scans.add(scan)
        return scan

    def start(self, user: User, scan_id: str) -> Scan:
        scan = self.get(user, scan_id)
        if scan.status not in (ScanStatus.UPLOADED, ScanStatus.FAILED):
            raise errors.ScanStateConflict()
        scan.status, scan.progress, scan.error = ScanStatus.QUEUED, 0.0, None
        self._scans.update(scan)
        self._queue.enqueue(scan.id)
        return scan

    def get(self, user: User, scan_id: str) -> Scan:
        scan = self._scans.get(scan_id)
        if scan is None or (scan.user_id != user.id and user.role is not Role.ADMIN):
            raise errors.ScanNotFound()  # do not reveal that someone else's scan exists
        return scan

    def history(self, user: User, criteria: ScanFilter) -> tuple[list[Scan], int]:
        return self._scans.search(user.id, criteria)

    def stats(self, user: User) -> dict[str, int]:
        return self._scans.stats(user.id)

    def delete(self, user: User, scan_id: str) -> None:
        scan = self.get(user, scan_id)
        if scan.status.is_active:
            raise errors.ScanStateConflict()
        self._scans.delete(scan.id)
        self._storage.delete_scan(scan.id, scan.stored_name)

    def source_path(self, user: User, scan_id: str) -> tuple[Scan, Path]:
        scan = self.get(user, scan_id)
        path = self._storage.upload_path(scan.stored_name)
        if not path.is_file():
            raise errors.ScanNotFound()
        return scan, path

    def artifact_path(self, user: User, scan_id: str, name: str) -> Path:
        scan = self.get(user, scan_id)
        path = self._storage.artifact(scan.id, name)
        if path is None:
            raise errors.ScanNotFound()
        return path

    def artifacts_dir(self, scan: Scan) -> Path:
        return self._storage.scan_dir(scan.id)


def _modality(result: ModalityResult | None) -> tuple[dict[str, Any] | None, Verdict | None]:
    if result is None:
        return None, None
    uncapped = classify(result.prob_fake, result.thresholds)
    verdict = cap(uncapped, result.max_verdict)
    return {
        "prob": result.prob_fake,
        "verdict": verdict.value,
        "capped": verdict is not uncapped,
        "real_max": result.thresholds.real_max,
        "fake_min": result.thresholds.fake_min,
        "model": result.model,
        "provisional": result.provisional,
    }, verdict


def apply_analysis(scan: Scan, analysis: Analysis) -> None:
    """Derive verdicts from raw analysis output and write them onto the scan."""
    visual, visual_verdict = _modality(analysis.visual)
    audio, audio_verdict = _modality(analysis.audio)
    scan.visual_prob = analysis.visual.prob_fake if analysis.visual else None
    scan.audio_prob = analysis.audio.prob_fake if analysis.audio else None
    scan.verdict = fuse(scan.media_type, visual_verdict, audio_verdict)
    scan.prob_fake = headline_probability(scan.visual_prob, scan.audio_prob, scan.media_type)
    scan.details = {
        "media": {**scan.details.get("media", {}), **analysis.media_info},
        "visual": visual,
        "audio": audio,
        "frames": [
            {
                "index": f.index,
                "t": f.timestamp_s,
                "prob": f.prob_fake,
                "box": list(f.box) if f.box else None,
                "face": f.face_file,
                "heatmap": f.heatmap_file,
            }
            for f in analysis.frames
        ],
        "segments": [
            {"start": s.start_s, "end": s.end_s, "prob": s.prob_fake} for s in analysis.segments
        ],
        "notes": list(analysis.notes),
        "overview": analysis.overview_file,
    }


class ScanProcessor:
    """Runs one queued scan to completion. Never raises: failures end up on the scan."""

    def __init__(
        self,
        scans: ScanRepository,
        storage: FileStorage,
        analyzer: MediaAnalyzer,
        events: EventPublisher,
    ) -> None:
        self._scans = scans
        self._storage = storage
        self._analyzer = analyzer
        self._events = events

    def _publish(self, scan: Scan) -> None:
        self._events.publish(
            scan.id,
            {
                "status": scan.status.value,
                "progress": round(scan.progress, 4),
                "verdict": scan.verdict.value if scan.verdict else None,
                "error": scan.error,
            },
        )

    def process(self, scan_id: str) -> None:
        scan = self._scans.get(scan_id)
        if scan is None or scan.status.is_terminal:
            return
        started = time.monotonic()

        def progress(status: ScanStatus, fraction: float) -> None:
            scan.status, scan.progress = status, max(0.0, min(1.0, fraction))
            self._scans.update(scan)
            self._publish(scan)

        try:
            progress(ScanStatus.PREPROCESSING, 0.02)
            analysis = self._analyzer.analyze(
                self._storage.upload_path(scan.stored_name),
                scan.media_type,
                self._storage.scan_dir(scan.id),
                progress,
            )
            apply_analysis(scan, analysis)
            scan.status, scan.progress = ScanStatus.DONE, 1.0
        except errors.DomainError as error:
            scan.status, scan.error = ScanStatus.FAILED, error.code
        except Exception:
            log.exception("scan %s crashed", scan_id)
            scan.status, scan.error = ScanStatus.FAILED, "internal_error"
        scan.finished_at = _now()
        scan.duration_ms = int((time.monotonic() - started) * 1000)
        self._scans.update(scan)
        self._publish(scan)
        log.info(
            "scan %s finished: status=%s verdict=%s in %d ms",
            scan.id,
            scan.status.value,
            scan.verdict,
            scan.duration_ms,
        )


def media_type_of(value: str | None) -> MediaType | None:
    return MediaType(value) if value else None
