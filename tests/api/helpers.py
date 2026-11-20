from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def upload(client: TestClient, auth: dict[str, str], path: Path, name: str | None = None) -> Any:
    with path.open("rb") as handle:
        return client.post("/api/scans", files={"file": (name or path.name, handle)}, headers=auth)


def run_scan(
    client: TestClient, auth: dict[str, str], path: Path, timeout: float = 120.0
) -> dict[str, Any]:
    """Upload, start and wait for a scan; returns the final scan document."""
    created = upload(client, auth, path)
    assert created.status_code == 201, created.text
    scan_id = created.json()["id"]
    started = client.post(f"/api/scans/{scan_id}/start", headers=auth)
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scan: dict[str, Any] = client.get(f"/api/scans/{scan_id}", headers=auth).json()
        if scan["status"] in {"done", "failed"}:
            return scan
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")
