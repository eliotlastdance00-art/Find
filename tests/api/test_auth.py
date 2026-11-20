from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dfd.container import build_container
from dfd.presentation.app import create_app
from tests.conftest import PASSWORD, CentreFace, make_settings, register


def error_code(response: object) -> str:
    return str(response.json()["error"]["code"])  # type: ignore[attr-defined]


def test_first_account_is_admin_then_users(client: TestClient) -> None:
    first = client.post("/api/auth/register", json={"username": "boss", "password": PASSWORD})
    second = client.post("/api/auth/register", json={"username": "worker", "password": PASSWORD})
    assert first.status_code == second.status_code == 201
    assert first.json()["user"]["role"] == "admin"
    assert second.json()["user"]["role"] == "user"
    assert first.json()["expires_in"] == 12 * 3600
    assert "password" not in first.text


def test_login_and_me(client: TestClient) -> None:
    register(client, "eliot")
    session = client.post("/api/auth/login", json={"username": "Eliot", "password": PASSWORD})
    assert session.status_code == 200
    headers = {"Authorization": f"Bearer {session.json()['token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["username"] == "eliot"


def test_wrong_password_and_unknown_user_look_the_same(client: TestClient) -> None:
    register(client, "eliot")
    wrong = client.post("/api/auth/login", json={"username": "eliot", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert error_code(wrong) == "invalid_credentials"


@pytest.mark.parametrize(
    ("username", "password", "code", "status"),
    [
        ("ab", PASSWORD, "invalid_username", 422),
        ("bad name!", PASSWORD, "invalid_username", 422),
        ("eliot", "short", "weak_password", 422),
        ("eliot", "eliot", "weak_password", 422),
    ],
)
def test_registration_validation(
    client: TestClient, username: str, password: str, code: str, status: int
) -> None:
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == status
    assert error_code(response) == code


def test_duplicate_username_is_rejected_case_insensitively(client: TestClient) -> None:
    register(client, "eliot")
    again = client.post("/api/auth/register", json={"username": "ELIOT", "password": PASSWORD})
    assert again.status_code == 409 and error_code(again) == "username_taken"


def test_protected_routes_need_a_valid_token(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer nonsense"}, {"Authorization": "Basic abc"}):
        response = client.get("/api/scans", headers=headers)
        assert response.status_code == 401
        assert error_code(response) == "not_authenticated"


def test_login_is_rate_limited(client: TestClient) -> None:
    register(client, "eliot")
    codes = [
        client.post("/api/auth/login", json={"username": "eliot", "password": "x" * 9}).status_code
        for _ in range(10)
    ]
    assert codes[:8] == [401] * 8
    assert codes[-1] == 429
    blocked = client.post("/api/auth/login", json={"username": "eliot", "password": PASSWORD})
    assert blocked.status_code == 429 and error_code(blocked) == "too_many_attempts"


def test_closed_registration_still_allows_bootstrap(tmp_path: Path, weights_dir: Path) -> None:
    settings = make_settings(tmp_path, weights_dir, allow_registration=False)
    with TestClient(create_app(container=build_container(settings, CentreFace()))) as client:
        assert client.get("/api/meta").json()["registration_open"] is True
        register(client, "boss")
        assert client.get("/api/meta").json()["registration_open"] is False
        closed = client.post("/api/auth/register", json={"username": "late", "password": PASSWORD})
        assert closed.status_code == 403 and error_code(closed) == "registration_closed"


def test_admin_from_environment(tmp_path: Path, weights_dir: Path) -> None:
    settings = make_settings(tmp_path, weights_dir, admin_username="root", admin_password=PASSWORD)
    with TestClient(create_app(container=build_container(settings, CentreFace()))) as client:
        session = client.post("/api/auth/login", json={"username": "root", "password": PASSWORD})
        assert session.status_code == 200 and session.json()["user"]["role"] == "admin"
