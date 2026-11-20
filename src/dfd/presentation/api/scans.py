from __future__ import annotations

import asyncio
import json
import mimetypes
from collections.abc import AsyncIterator, Mapping
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from dfd.domain import errors
from dfd.domain.entities import MediaType, Scan, ScanStatus, User, Verdict
from dfd.domain.ports import ScanFilter
from dfd.infrastructure.report.texts import DEFAULT_LANGUAGE, LANGUAGES
from dfd.presentation.deps import ContainerDep, CurrentUser, MediaUser
from dfd.presentation.schemas import HistoryOut, ScanOut, ScanSummary

router = APIRouter(prefix="/api", tags=["scans"])
HEARTBEAT_S = 15.0


def _out(container: ContainerDep, user: User, scan: Scan) -> ScanOut:
    return ScanOut.build(scan, container.auth.media_token(user, scan.id))


@router.post("/scans", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
def upload(
    file: UploadFile, request: Request, user: CurrentUser, container: ContainerDep
) -> ScanOut:
    """Upload a file. It is validated and stored; analysis starts with ``/start``."""
    declared = request.headers.get("content-length")
    limit = container.settings.max_upload_bytes
    if declared and declared.isdigit() and int(declared) > limit + 64 * 1024:
        raise errors.FileTooLarge(limit_bytes=limit)
    scan = container.scan_service.upload(user, file.filename or "file", file.file)
    return _out(container, user, scan)


@router.post("/scans/{scan_id}/start", response_model=ScanOut, status_code=status.HTTP_202_ACCEPTED)
def start(scan_id: str, user: CurrentUser, container: ContainerDep) -> ScanOut:
    return _out(container, user, container.scan_service.start(user, scan_id))


@router.get("/scans", response_model=HistoryOut)
def history(
    user: CurrentUser,
    container: ContainerDep,
    verdict: Verdict | None = None,
    media_type: MediaType | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryOut:
    criteria = ScanFilter(verdict, media_type, q.strip() if q else None, limit, offset)
    scans, total = container.scan_service.history(user, criteria)
    return HistoryOut(
        items=[ScanSummary.of(s) for s in scans], total=total, limit=limit, offset=offset
    )


@router.get("/stats")
def stats(user: CurrentUser, container: ContainerDep) -> dict[str, int]:
    return container.scan_service.stats(user)


@router.get("/scans/{scan_id}", response_model=ScanOut)
def detail(scan_id: str, user: CurrentUser, container: ContainerDep) -> ScanOut:
    return _out(container, user, container.scan_service.get(user, scan_id))


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(scan_id: str, user: CurrentUser, container: ContainerDep) -> Response:
    container.scan_service.delete(user, scan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _sse(payload: Mapping[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.get("/scans/{scan_id}/events")
async def events(scan_id: str, user: CurrentUser, container: ContainerDep) -> StreamingResponse:
    """Server-sent events with live status and progress until the scan finishes."""
    scan = await run_in_threadpool(container.scan_service.get, user, scan_id)
    channel = container.events.subscribe(scan_id)

    async def stream() -> AsyncIterator[str]:
        try:
            # Re-read after subscribing so a scan that just finished is not missed.
            current = await run_in_threadpool(container.scan_service.get, user, scan_id)
            snapshot = {
                "status": current.status.value,
                "progress": current.progress,
                "verdict": current.verdict.value if current.verdict else None,
                "error": current.error,
            }
            yield _sse(snapshot)
            if current.status.is_terminal:
                return
            while True:
                try:
                    event = await asyncio.wait_for(channel.get(), HEARTBEAT_S)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if ScanStatus(event["status"]).is_terminal:
                    return
        finally:
            container.events.unsubscribe(scan_id, channel)

    del scan
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


@router.get("/scans/{scan_id}/source")
def source(scan_id: str, user: MediaUser, container: ContainerDep) -> FileResponse:
    """The original upload, for the in-browser preview."""
    scan, path = container.scan_service.source_path(user, scan_id)
    media_type = mimetypes.guess_type(scan.filename)[0] or "application/octet-stream"
    if not media_type.startswith(("image/", "video/", "audio/")):
        media_type = "application/octet-stream"
    return FileResponse(
        path, media_type=media_type, headers={"Cache-Control": "private, max-age=600"}
    )


@router.get("/scans/{scan_id}/files/{name}")
def artifact(scan_id: str, name: str, user: MediaUser, container: ContainerDep) -> FileResponse:
    path = container.scan_service.artifact_path(user, scan_id, name)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/scans/{scan_id}/report.pdf")
def report(
    scan_id: str,
    user: MediaUser,
    container: ContainerDep,
    lang: Annotated[str, Query(max_length=5)] = DEFAULT_LANGUAGE,
    download: bool = False,
) -> Response:
    scan = container.scan_service.get(user, scan_id)
    if scan.status is not ScanStatus.DONE:
        raise errors.ScanStateConflict()
    owner = container.users.get(scan.user_id)
    pdf = container.reports.render(
        scan,
        owner.username if owner else "-",
        lang if lang in LANGUAGES else DEFAULT_LANGUAGE,
        container.scan_service.artifacts_dir(scan),
    )
    disposition = "attachment" if download else "inline"
    filename = quote(f"dfd-report-{scan.id[:8]}.pdf")
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
