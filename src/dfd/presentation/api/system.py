from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from dfd import __version__
from dfd.infrastructure.report.texts import LANGUAGES
from dfd.presentation.deps import ContainerDep

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(container: ContainerDep) -> dict[str, Any]:
    """Liveness plus which models are installed (the app runs without them, scans do not)."""
    models = container.registry.status()
    return {
        "status": "ok",
        "version": __version__,
        "models": {kind: bool(info.get("available")) for kind, info in models.items()},
    }


@router.get("/meta")
def meta(container: ContainerDep) -> dict[str, Any]:
    settings = container.settings
    return {
        "version": __version__,
        "languages": list(LANGUAGES),
        "limits": {
            "max_upload_mb": settings.max_upload_mb,
            "max_duration_s": settings.max_duration_s,
        },
        "registration_open": settings.allow_registration or container.users.count() == 0,
        "models": container.registry.status(),
    }
