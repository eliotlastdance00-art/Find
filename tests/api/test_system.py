from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dfd import __version__
from dfd.container import build_container
from dfd.presentation.app import create_app
from tests.api.helpers import upload
from tests.conftest import CentreFace, make_settings, register


def test_health_and_meta(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["version"] == __version__
    assert health["models"] == {"visual": True, "audio": True}
    meta = client.get("/api/meta").json()
    assert meta["languages"] == ["tk", "ru", "en"]
    assert meta["limits"] == {"max_upload_mb": 200, "max_duration_s": 600}
    assert meta["registration_open"] is True
    assert meta["models"]["visual"]["name"] == "tiny-visual"


def test_index_and_static_assets(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200 and "text/html" in index.headers["content-type"]
    assert '<script type="module" src="/static/js/app.js">' in index.text
    assets = [
        "app",
        "api",
        "views",
        "ui",
        "i18n",
        "motion",
        "theme",
        "logo",
        "fx",
        "menus",
        "sleuth",
    ]
    for asset in (
        *(f"js/{name}.js" for name in assets),
        "css/app.css",
        "css/world.css",
        "favicon.svg",
    ):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200, asset
        # Unversioned file names: the browser must revalidate, or an update shows a stale UI.
        assert response.headers["cache-control"] == "no-cache", asset
    assert client.get("/favicon.ico").status_code == 200


def test_security_headers(client: TestClient) -> None:
    response = client.get("/")
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "'unsafe-eval'" not in policy
    assert "frame-ancestors 'self'" in policy and "object-src 'none'" in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


def test_request_id_is_echoed_only_when_well_formed(client: TestClient) -> None:
    good = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert good.headers["x-request-id"] == "abc-123"
    bad = client.get("/api/health", headers={"X-Request-ID": "x" * 200})
    assert bad.headers["x-request-id"] != "x" * 200


def test_unknown_api_route_and_validation_errors_use_the_error_envelope(
    client: TestClient,
) -> None:
    missing = client.get("/api/nope")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    wrong_method = client.delete("/api/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"
    invalid = client.post("/api/auth/login", json={"username": "x"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_openapi_schema_is_served(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    assert "/api/scans/{scan_id}/report.pdf" in schema["paths"]


def test_scans_fail_cleanly_without_models(tmp_path: Path, media: dict[str, Path]) -> None:
    settings = make_settings(tmp_path, tmp_path / "no-weights")
    with TestClient(create_app(container=build_container(settings, CentreFace()))) as client:
        assert client.get("/api/health").json()["models"] == {"visual": False, "audio": False}
        auth = register(client)
        scan_id = upload(client, auth, media["image"]).json()["id"]
        client.post(f"/api/scans/{scan_id}/start", headers=auth)
        for _ in range(200):
            scan = client.get(f"/api/scans/{scan_id}", headers=auth).json()
            if scan["status"] in {"done", "failed"}:
                break
        assert scan["status"] == "failed" and scan["error"] == "model_unavailable"
