from __future__ import annotations

from fastapi import APIRouter, Request, status

from dfd.domain.entities import User
from dfd.presentation.deps import ContainerDep, CurrentUser, client_address
from dfd.presentation.schemas import Credentials, SessionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session(container: ContainerDep, user: User, token: str) -> SessionOut:
    ttl = container.settings.token_ttl_hours * 3600
    return SessionOut(user=UserOut.of(user), token=token, expires_in=ttl)


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, container: ContainerDep) -> SessionOut:
    user, token = container.auth.register(body.username, body.password)
    return _session(container, user, token)


@router.post("/login", response_model=SessionOut)
def login(body: Credentials, request: Request, container: ContainerDep) -> SessionOut:
    user, token = container.auth.login(body.username, body.password, client_address(request))
    return _session(container, user, token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)
