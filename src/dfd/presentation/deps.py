"""FastAPI dependencies: container access and authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from dfd.container import Container
from dfd.domain import errors
from dfd.domain.entities import User


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def bearer_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value else None


def current_user(request: Request, container: ContainerDep) -> User:
    return container.auth.authenticate(bearer_token(request))


def media_user(
    scan_id: str,
    request: Request,
    container: ContainerDep,
    t: Annotated[str | None, Query(max_length=1024)] = None,
) -> User:
    """Accept the session token, or a media token scoped to this scan (for <img>/<video>)."""
    token = bearer_token(request)
    if token:
        return container.auth.authenticate(token)
    if t:
        return container.auth.authenticate_media(t, scan_id)
    raise errors.NotAuthenticated()


CurrentUser = Annotated[User, Depends(current_user)]
MediaUser = Annotated[User, Depends(media_user)]


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"
