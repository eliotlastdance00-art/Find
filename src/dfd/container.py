"""Composition root: the only place where concrete implementations are wired together."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Engine

from dfd.application.auth import AuthService
from dfd.application.scans import ScanProcessor, ScanService
from dfd.config import Settings
from dfd.domain.ports import ReportRenderer, ScanRepository, UserRepository
from dfd.infrastructure.analysis import TorchMediaAnalyzer
from dfd.infrastructure.db.repositories import SqlScanRepository, SqlUserRepository
from dfd.infrastructure.db.session import create_session_factory
from dfd.infrastructure.jobs import EventBroker, WorkerPool
from dfd.infrastructure.media.faces import FaceDetector
from dfd.infrastructure.media.inspect import FileInspector
from dfd.infrastructure.ml.registry import ModelRegistry
from dfd.infrastructure.report.pdf import PdfReportRenderer
from dfd.infrastructure.security import Argon2PasswordHasher, JwtTokenService, SlidingWindowLimiter
from dfd.infrastructure.storage import LocalFileStorage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: Engine
    users: UserRepository
    scans: ScanRepository
    auth: AuthService
    scan_service: ScanService
    processor: ScanProcessor
    workers: WorkerPool
    events: EventBroker
    registry: ModelRegistry
    reports: ReportRenderer

    def start(self) -> None:
        """Start background workers and resume scans interrupted by a restart."""
        settings = self.settings
        self.auth.ensure_admin(settings.admin_username, settings.admin_password)
        if settings.preload_models:
            self.registry.preload()
        self.workers.start()
        for scan in self.scans.list_active():
            log.info("re-queueing interrupted scan %s", scan.id)
            self.workers.enqueue(scan.id)

    def stop(self) -> None:
        self.workers.stop()
        self.engine.dispose()


def build_container(settings: Settings, faces: FaceDetector | None = None) -> Container:
    """Wire the application. ``faces`` lets tests substitute the face detector."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.torch_threads:
        import torch  # noqa: PLC0415

        torch.set_num_threads(settings.torch_threads)

    engine, sessions = create_session_factory(settings.resolved_database_url())
    users, scans = SqlUserRepository(sessions), SqlScanRepository(sessions)
    storage = LocalFileStorage(settings.uploads_dir, settings.scans_dir)
    registry = ModelRegistry(settings.weights_dir, settings.device)
    analyzer = TorchMediaAnalyzer(
        registry,
        faces or FaceDetector(),
        video_frames=settings.video_frames,
        explain_top_k=settings.explain_top_k,
        max_faces=settings.max_faces,
        max_audio_s=float(settings.max_duration_s),
        analyze_video_audio=settings.analyze_video_audio,
    )
    events = EventBroker()
    processor = ScanProcessor(scans, storage, analyzer, events)
    workers = WorkerPool(processor.process, settings.workers)
    auth = AuthService(
        users,
        Argon2PasswordHasher(),
        JwtTokenService(settings.resolved_secret_key(), settings.token_ttl_hours),
        SlidingWindowLimiter(),
        settings.allow_registration,
    )
    scan_service = ScanService(
        scans,
        storage,
        FileInspector(),
        workers,
        settings.max_upload_bytes,
        float(settings.max_duration_s),
    )
    return Container(
        settings=settings,
        engine=engine,
        users=users,
        scans=scans,
        auth=auth,
        scan_service=scan_service,
        processor=processor,
        workers=workers,
        events=events,
        registry=registry,
        reports=PdfReportRenderer(),
    )
