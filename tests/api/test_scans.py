from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dfd.container import build_container
from dfd.presentation.app import create_app
from tests.api.helpers import run_scan, upload
from tests.conftest import CentreFace, make_settings, register

VERDICTS = {"real", "suspicious", "fake"}


def test_upload_validates_content_not_extension(
    client: TestClient, auth: dict[str, str], media: dict[str, Path], tmp_path: Path
) -> None:
    disguised = upload(client, auth, media["text"], "holiday.jpg")
    assert disguised.status_code == 415
    assert disguised.json()["error"]["code"] == "unsupported_media"

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert upload(client, auth, empty).json()["error"]["code"] == "empty_file"

    renamed = upload(client, auth, media["image"], "actually-a-photo.bin")
    assert renamed.status_code == 201 and renamed.json()["media_type"] == "image"
    assert (
        client.get("/api/stats", headers=auth).json()["total"] == 1
    )  # rejected files leave nothing


def test_upload_returns_metadata(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = upload(client, auth, media["video"]).json()
    assert scan["status"] == "uploaded" and scan["media_type"] == "video"
    assert scan["filename"] == "clip.mp4"
    assert scan["size_bytes"] == media["video"].stat().st_size
    assert len(scan["sha256"]) == 64 and scan["verdict"] is None
    info = scan["details"]["media"]
    assert (info["width"], info["height"], info["has_audio"]) == (320, 240, True)
    assert scan["created_at"].endswith("Z")


def test_image_scan_end_to_end(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = run_scan(client, auth, media["image"])
    assert scan["status"] == "done", scan
    assert scan["verdict"] in VERDICTS and 0.0 <= scan["prob_fake"] <= 1.0
    assert scan["progress"] == 1.0 and scan["duration_ms"] > 0
    assert scan["audio_prob"] is None and scan["visual_prob"] == scan["prob_fake"]
    details = scan["details"]
    assert details["visual"]["model"] == "tiny-visual 0.0.1" and details["visual"]["provisional"]
    assert details["media"]["faces_found"] == 1 and len(details["frames"]) == 1
    token = scan["media_token"]
    for name in (
        details["overview"],
        details["frames"][0]["face"],
        details["frames"][0]["heatmap"],
    ):
        picture = client.get(f"/api/scans/{scan['id']}/files/{name}?t={token}")
        assert picture.status_code == 200 and picture.content[:3] == b"\xff\xd8\xff"


def test_video_scan_combines_picture_and_sound(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = run_scan(client, auth, media["video"])
    assert scan["status"] == "done", scan
    details = scan["details"]
    assert details["media"]["frames_sampled"] == 6 and details["media"]["faces_found"] == 6
    assert len(details["frames"]) == 6
    assert sum(1 for f in details["frames"] if f["heatmap"]) == 2  # explain_top_k
    assert details["audio"] is not None and len(details["segments"]) >= 1
    assert scan["prob_fake"] == scan["visual_prob"]
    if details["visual"]["verdict"] == "real" and details["audio"]["verdict"] == "fake":
        assert scan["verdict"] == "suspicious"


def test_mute_video_has_no_audio_result(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = run_scan(client, auth, media["mute_video"])
    assert scan["status"] == "done"
    assert scan["details"]["audio"] is None and scan["audio_prob"] is None


def test_audio_scan_and_silence(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = run_scan(client, auth, media["audio"])
    assert scan["status"] == "done" and scan["verdict"] in VERDICTS
    assert scan["visual_prob"] is None and scan["prob_fake"] == scan["audio_prob"]
    assert scan["details"]["frames"] == [] and len(scan["details"]["segments"]) == 1

    silent = run_scan(client, auth, media["silence"])
    assert silent["status"] == "done" and silent["verdict"] == "inconclusive"
    assert silent["prob_fake"] is None and "audio_silent" in silent["details"]["notes"]


def test_capped_audio_model_never_says_fake_and_explains_why(
    tmp_path: Path, weights_dir: Path, media: dict[str, Path]
) -> None:
    weights = tmp_path / "weights"
    shutil.copytree(weights_dir, weights)
    card = weights / "audio" / "model_card.json"
    data = json.loads(card.read_text())
    data["thresholds"] = {"audio": {"real_max": 0.0, "fake_min": 0.0}}  # anything is "fake"
    data["max_verdict"] = "suspicious"
    card.write_text(json.dumps(data))
    container = build_container(make_settings(tmp_path, weights), faces=CentreFace())
    with TestClient(create_app(container=container)) as capped:
        auth = register(capped)
        scan = run_scan(capped, auth, media["audio"])
        assert scan["status"] == "done" and scan["verdict"] == "suspicious"
        assert scan["details"]["audio"]["capped"] is True
        assert "audio_capped" in scan["details"]["notes"]
        report = capped.get(f"/api/scans/{scan['id']}/report.pdf?lang=tk", headers=auth)
        assert report.status_code == 200 and report.content.startswith(b"%PDF")


def test_events_stream_reports_progress_until_done(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan_id = upload(client, auth, media["image"]).json()["id"]
    client.post(f"/api/scans/{scan_id}/start", headers=auth)
    events = []
    with client.stream("GET", f"/api/scans/{scan_id}/events", headers=auth) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    assert events[-1]["status"] == "done" and events[-1]["verdict"] in VERDICTS
    progress = [event["progress"] for event in events]
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert client.get(f"/api/scans/{scan_id}/events").status_code == 401


def test_scan_state_rules(client: TestClient, auth: dict[str, str], media: dict[str, Path]) -> None:
    scan_id = upload(client, auth, media["image"]).json()["id"]
    early = client.get(f"/api/scans/{scan_id}/report.pdf", headers=auth)
    assert early.status_code == 409 and early.json()["error"]["code"] == "scan_state_conflict"
    done = run_scan(client, auth, media["image"])
    again = client.post(f"/api/scans/{done['id']}/start", headers=auth)
    assert again.status_code == 409
    assert client.post("/api/scans/does-not-exist/start", headers=auth).status_code == 404


@pytest.mark.parametrize("lang", ["tk", "ru", "en"])
def test_report_pdf_in_every_language(
    client: TestClient, auth: dict[str, str], media: dict[str, Path], lang: str
) -> None:
    scan = run_scan(client, auth, media["video"])
    url = f"/api/scans/{scan['id']}/report.pdf?lang={lang}"
    inline = client.get(url, headers=auth)
    assert inline.status_code == 200 and inline.content.startswith(b"%PDF-")
    assert inline.headers["content-type"] == "application/pdf"
    assert inline.headers["content-disposition"].startswith("inline")
    assert "object-src" not in inline.headers["content-security-policy"]
    assert len(inline.content) > 10_000
    download = client.get(f"{url}&download=true&t={scan['media_token']}")
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment")


def test_report_falls_back_to_default_language(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    scan = run_scan(client, auth, media["image"])
    response = client.get(f"/api/scans/{scan['id']}/report.pdf?lang=xx", headers=auth)
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")


def test_media_endpoints_need_the_scan_token(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    first = run_scan(client, auth, media["image"])
    second = run_scan(client, auth, media["png"])
    source = f"/api/scans/{first['id']}/source"
    assert client.get(source).status_code == 401
    assert client.get(f"{source}?t=garbage").status_code == 401
    assert client.get(f"{source}?t={second['media_token']}").status_code == 401  # other scan
    ok = client.get(f"{source}?t={first['media_token']}")
    assert ok.status_code == 200 and ok.content == media["image"].read_bytes()
    assert ok.headers["content-type"] == "image/jpeg"
    assert client.get(source, headers=auth).status_code == 200
    # a media token is not a session token
    assert (
        client.get(
            "/api/scans", headers={"Authorization": f"Bearer {first['media_token']}"}
        ).status_code
        == 401
    )
    for name in ("..%2F..%2Fdfd.db", "audio.wav.exe", "nope.jpg"):
        hidden = client.get(f"/api/scans/{first['id']}/files/{name}?t={first['media_token']}")
        assert hidden.status_code == 404


def test_users_cannot_see_each_others_scans_but_admin_can(
    client: TestClient, media: dict[str, Path]
) -> None:
    admin = register(client, "boss")
    alice = register(client, "alice")
    bob = register(client, "bobby")
    scan_id = upload(client, alice, media["image"]).json()["id"]
    for method, path in (
        ("GET", f"/api/scans/{scan_id}"),
        ("POST", f"/api/scans/{scan_id}/start"),
        ("DELETE", f"/api/scans/{scan_id}"),
        ("GET", f"/api/scans/{scan_id}/source"),
    ):
        response = client.request(method, path, headers=bob)
        assert response.status_code == 404, (method, path)
        assert response.json()["error"]["code"] == "scan_not_found"
    assert client.get("/api/scans", headers=bob).json()["total"] == 0
    assert client.get("/api/stats", headers=bob).json()["total"] == 0
    assert client.get(f"/api/scans/{scan_id}", headers=admin).status_code == 200


def test_history_filters_pagination_stats_and_delete(
    client: TestClient, auth: dict[str, str], media: dict[str, Path]
) -> None:
    image = run_scan(client, auth, media["image"])
    run_scan(client, auth, media["silence"])
    pending = upload(client, auth, media["png"]).json()

    everything = client.get("/api/scans", headers=auth).json()
    assert everything["total"] == 3
    assert everything["items"][0]["id"] == pending["id"]  # newest first
    assert "details" not in everything["items"][0]

    def total(**params: object) -> int:
        return int(client.get("/api/scans", params=params, headers=auth).json()["total"])

    assert total(media_type="audio") == 1 and total(media_type="image") == 2
    assert total(verdict="inconclusive") == 1
    assert total(q="PHOTO") == 2 and total(q="100%_") == 0
    page = client.get("/api/scans", params={"limit": 2, "offset": 2}, headers=auth).json()
    assert len(page["items"]) == 1 and page["total"] == 3
    assert client.get("/api/scans?limit=1000", headers=auth).status_code == 422
    assert client.get("/api/scans?verdict=maybe", headers=auth).status_code == 422

    stats = client.get("/api/stats", headers=auth).json()
    assert stats["total"] == 3 and stats["inconclusive"] == 1
    assert stats["real"] + stats["suspicious"] + stats["fake"] == 1

    token = image["media_token"]
    assert client.delete(f"/api/scans/{image['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/scans/{image['id']}", headers=auth).status_code == 404
    assert client.get(f"/api/scans/{image['id']}/source?t={token}").status_code == 404
    assert total() == 2


def test_upload_size_limit(tmp_path: Path, weights_dir: Path, media: dict[str, Path]) -> None:
    from dfd.container import build_container  # noqa: PLC0415
    from dfd.presentation.app import create_app  # noqa: PLC0415
    from tests.conftest import CentreFace, make_settings  # noqa: PLC0415

    settings = make_settings(tmp_path, weights_dir, max_upload_mb=1)
    big = tmp_path / "big.wav"
    big.write_bytes(media["audio"].read_bytes() + b"\0" * (2 << 20))
    with TestClient(create_app(container=build_container(settings, CentreFace()))) as client:
        auth = register(client)
        response = upload(client, auth, big)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"
        assert list(settings.uploads_dir.iterdir()) == []
