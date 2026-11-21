"""FastAPI application factory."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from dfd import __version__
from dfd.config import Settings
from dfd.container import Container, build_container
from dfd.domain.errors import DomainError
from dfd.logging_setup import configure_logging
from dfd.presentation.api import auth, scans, system

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("dfd.http")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _error(status: int, code: str, message: str, **params: object) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "params": params}}
    return JSONResponse(body, status_code=status)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or (container.settings if container else Settings())
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or build_container(settings)
        app.state.container.start()
        try:
            yield
        finally:
            app.state.container.stop()

    app = FastAPI(
        title="Deepfake Detection System",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    csp = (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; "
        f"base-uri 'self'; form-action 'self'; frame-ancestors {settings.frame_ancestors}"
    )
    # Browsers' built-in PDF viewers are plugins: the page policy would stop them rendering.
    pdf_csp = f"frame-ancestors {settings.frame_ancestors}"

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if response.headers.get("content-type", "").startswith("application/pdf"):
            response.headers["Content-Security-Policy"] = pdf_csp
        elif not request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = csp
        if request.url.path.startswith("/static/"):
            # Always revalidate: a new release must not run with a cached older script.
            response.headers["Cache-Control"] = "no-cache"
        if request.url.path.startswith("/api/"):
            log.info(
                "%s %s -> %d in %.0f ms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                extra={"request_id": request_id},
            )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, error: DomainError) -> JSONResponse:
        return _error(error.http_status, error.code, str(error), **error.params)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e["loc"][1:]) for e in error.errors()]
        return _error(422, "validation_error", "invalid request", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        code = codes.get(error.status_code, "error")
        return _error(error.status_code, code, str(error.detail))

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, error: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=error)
        return _error(500, "internal_error", "internal error")

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(scans.router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")

    return app
