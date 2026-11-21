#!/usr/bin/env python3
"""Black-box smoke test of a running instance, standard library only.

    python scripts/smoke_test.py http://localhost:8000

Registers an account, scans a generated WAV tone and a generated PNG, downloads the PDF
report and checks the web page. Used by CI against the Docker image.
"""

from __future__ import annotations

import io
import json
import math
import os
import secrets
import struct
import sys
import time
import urllib.error
import urllib.request
import wave
import zlib
from typing import Any

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def call(
    method: str, path: str, token: str | None = None, body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, bytes]:  # fmt: skip
    request = urllib.request.Request(BASE + path, data=body, method=method)
    for line in filter(None, os.environ.get("SMOKE_HEADERS", "").split("\n")):
        name, _, value = line.partition(":")  # e.g. the token a private forwarded port wants
        request.add_header(name.strip(), value.strip())
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def post_json(path: str, payload: dict[str, Any], token: str | None = None) -> tuple[int, Any]:
    status, raw = call("POST", path, token, json.dumps(payload).encode(), "application/json")
    return status, json.loads(raw)


def get_json(path: str, token: str | None = None) -> Any:
    status, raw = call("GET", path, token)
    assert status == 200, (path, status, raw[:200])
    return json.loads(raw)


def wav_tone(seconds: float = 2.0, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(9000 * math.sin(2 * math.pi * 220 * i / rate)))
                for i in range(int(seconds * rate))
            )
        )
    return buffer.getvalue()


def png_gradient(width: int = 160, height: int = 120) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(
        b"\x00" + bytes(v for x in range(width) for v in (x % 256, y % 256, (x + y) % 256))
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def scan(token: str, filename: str, content: bytes) -> dict[str, Any]:
    boundary = secrets.token_hex(16)
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    )
    body = head.encode() + content + f"\r\n--{boundary}--\r\n".encode()
    status, raw = call(
        "POST", "/api/scans", token, body, f"multipart/form-data; boundary={boundary}"
    )
    assert status == 201, (status, raw[:300])
    scan_id = json.loads(raw)["id"]
    status, raw = call("POST", f"/api/scans/{scan_id}/start", token)
    assert status == 202, (status, raw[:300])
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        result: dict[str, Any] = get_json(f"/api/scans/{scan_id}", token)
        if result["status"] in {"done", "failed"}:
            return result
        time.sleep(1)
    raise AssertionError(f"{filename}: scan did not finish")


def main() -> None:
    deadline = time.monotonic() + 120
    while True:  # wait for the server to come up
        try:
            health = get_json("/api/health")
            break
        except (urllib.error.URLError, ConnectionError, AssertionError):
            if time.monotonic() > deadline:
                raise
            time.sleep(2)
    print("health:", health)
    assert health["status"] == "ok"

    status, page = call("GET", "/")
    assert status == 200 and b'src="/static/js/app.js"' in page
    assert call("GET", "/static/js/app.js")[0] == 200

    username = f"smoke_{secrets.token_hex(4)}"
    status, session = post_json(
        "/api/auth/register", {"username": username, "password": secrets.token_urlsafe(16)}
    )
    assert status == 201, session
    token = session["token"]

    if health["models"]["audio"]:
        audio = scan(token, "tone.wav", wav_tone())
        print("audio:", audio["status"], audio["verdict"], audio["prob_fake"], audio["error"])
        assert audio["status"] == "done", audio
        assert audio["verdict"] in {"real", "suspicious", "fake"}
        for lang in ("tk", "ru", "en"):
            status, pdf = call("GET", f"/api/scans/{audio['id']}/report.pdf?lang={lang}", token)
            assert status == 200 and pdf.startswith(b"%PDF-"), (lang, status)
        print("pdf reports: ok")
    else:
        print("audio model not installed: skipped")

    if health["models"]["visual"]:
        image = scan(token, "gradient.png", png_gradient())
        print("image:", image["status"], image["verdict"], image["details"]["notes"])
        assert image["status"] == "done", image
        # A synthetic gradient has no face, which the system must report honestly.
        assert image["verdict"] == "inconclusive"
        assert "no_face_found" in image["details"]["notes"]
    else:
        print("visual model not installed: skipped")

    history = get_json("/api/scans", token)
    print("history:", history["total"], "scan(s)")
    assert call("GET", "/api/scans")[0] == 401
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
