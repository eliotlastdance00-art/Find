"""The image branch, persistence and PDF with a deterministic AI-image detector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from dfd.container import build_container
from dfd.infrastructure.ml.download import smaug_card
from dfd.presentation.app import create_app
from tests.api.helpers import run_scan
from tests.conftest import CentreFace, make_settings, register


@pytest.mark.parametrize("lang", ["tk", "ru", "en"])
def test_image_ai_result_survives_api_history_and_pdf(
    tmp_path: Path, weights_dir: Path, media: dict[str, Path], lang: str
) -> None:
    container = build_container(make_settings(tmp_path, weights_dir), faces=CentreFace())
    synthetic = Mock()
    synthetic.card = smaug_card()
    synthetic.predict.return_value = 0.999
    container.registry._synthetic = synthetic
    with TestClient(create_app(container=container)) as client:
        auth = register(client)
        scan = run_scan(client, auth, media["image"])
        assert scan["status"] == "done" and scan["verdict"] == "fake"
        assert scan["prob_fake"] == 0.999
        assert scan["details"]["synthetic"]["model"] == "smaug-onnx 1.0.0"
        assert scan["details"]["synthetic"]["provisional"] is True
        assert scan["details"]["visual"]["model"] == "tiny-visual 0.0.1"
        assert "synthetic_heatmap" in scan["details"]["notes"]
        # Grad-CAM stays a face finding; no invented Smaug localisation.
        assert len(scan["details"]["frames"]) == 1
        assert scan["details"]["frames"][0]["heatmap"].startswith("heat_")
        history = client.get("/api/scans?verdict=fake", headers=auth).json()
        assert history["items"][0]["id"] == scan["id"]
        pdf = client.get(f"/api/scans/{scan['id']}/report.pdf?lang={lang}", headers=auth)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert len(pdf.content) > 10_000


def test_metadata_only_cannot_turn_a_real_prediction_into_fake(
    tmp_path: Path, weights_dir: Path
) -> None:
    info = PngInfo()
    info.add_text("Software", "ComfyUI")
    image = tmp_path / "not-proof.png"
    Image.new("RGB", (320, 240)).save(image, pnginfo=info)  # CentreFace finds no face
    container = build_container(make_settings(tmp_path, weights_dir), faces=CentreFace())
    container.registry._synthetic = Mock()
    container.registry._synthetic.card = smaug_card()
    container.registry._synthetic.predict.return_value = 0.01
    with TestClient(create_app(container=container)) as client:
        auth = register(client)
        scan = run_scan(client, auth, image)
        assert scan["verdict"] == "real" and scan["details"]["visual"] is None
        assert scan["details"]["provenance"] == ["ai_software"]
        assert "provenance_unverified" in scan["details"]["notes"]
        assert scan["details"]["frames"] == []
        pdf = client.get(f"/api/scans/{scan['id']}/report.pdf?lang=en", headers=auth)
        assert pdf.status_code == 200


def test_video_does_not_run_the_still_image_detector(
    tmp_path: Path, weights_dir: Path, media: dict[str, Path]
) -> None:
    container = build_container(make_settings(tmp_path, weights_dir), faces=CentreFace())
    synthetic = Mock()
    container.registry._synthetic = synthetic
    with TestClient(create_app(container=container)) as client:
        scan = run_scan(client, register(client), media["mute_video"])
        assert scan["status"] == "done" and scan["details"]["synthetic"] is None
        synthetic.predict.assert_not_called()
