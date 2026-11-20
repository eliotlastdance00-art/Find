"""Shared fixtures.

The suite runs the real pipeline (FFmpeg, OpenCV, PyTorch, Grad-CAM, PDF) on synthetic
media with tiny randomly initialised networks, so it needs no downloads and no GPU.
Only the face detector is replaced: a random picture contains no face for YuNet to find.
"""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

from dfd.config import Settings
from dfd.container import build_container
from dfd.domain.entities import Thresholds
from dfd.infrastructure.media.faces import Face, FaceDetector, Image
from dfd.infrastructure.media.ffmpeg import ffmpeg_exe
from dfd.infrastructure.ml.audio import build_aasist
from dfd.infrastructure.ml.cards import ModelCard, file_sha256, save_card
from dfd.infrastructure.ml.visual import build_backbone
from dfd.presentation.app import create_app

PASSWORD = "correct-horse-battery"


class CentreFace(FaceDetector):
    """Reports one face in the middle of every picture that is not uniformly dark."""

    def __init__(self) -> None:  # no ONNX model needed
        pass

    def detect(self, image: Image) -> list[Face]:
        if float(image.mean()) < 8.0:
            return []
        height, width = image.shape[:2]
        side = min(height, width) / 2
        return [Face((width - side) / 2, (height - side) / 2, side, side, 0.99)]


def _write_card(folder: Path, weights: Path, **fields: object) -> None:
    save_card(
        folder,
        ModelCard(weights_file=weights.name, sha256=file_sha256(weights), **fields),  # type: ignore[arg-type]
    )


@pytest.fixture(scope="session")
def weights_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("weights")
    torch.manual_seed(0)

    visual = root / "visual"
    visual.mkdir()
    torch.save(build_backbone("test_efficientnet").state_dict(), visual / "weights.pth")
    _write_card(
        visual,
        visual / "weights.pth",
        name="tiny-visual",
        version="0.0.1",
        kind="visual",
        arch="test_efficientnet",
        input_size=96,
        thresholds={"image": Thresholds(0.3, 0.7), "video": Thresholds(0.3, 0.7)},
        provisional=True,
    )

    audio = root / "audio"
    audio.mkdir()
    torch.save(build_aasist().state_dict(), audio / "weights.pth")
    _write_card(
        audio,
        audio / "weights.pth",
        name="tiny-audio",
        version="0.0.1",
        kind="audio",
        arch="AASIST",
        thresholds={"audio": Thresholds(0.3, 0.7)},
        provisional=True,
    )
    return root


def make_settings(tmp_path: Path, weights: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "data_dir": tmp_path / "data",
        "weights_dir": weights,
        "secret_key": "test-secret-key-0123456789abcdef0123456789",
        "video_frames": 6,
        "explain_top_k": 2,
        "device": "cpu",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path, weights_dir: Path) -> Settings:
    return make_settings(tmp_path, weights_dir)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    container = build_container(settings, faces=CentreFace())
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


def register(client: TestClient, username: str = "eliot") -> dict[str, str]:
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register(client)


# ---------------------------------------------------------------- synthetic media


def _picture(seed: int = 0, width: int = 320, height: int = 240) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = rng.integers(40, 220, (height, width, 3), dtype=np.uint8)
    return cv2.GaussianBlur(image, (0, 0), 3)


def _tone(path: Path, seconds: float, rate: int = 16000) -> None:
    t = np.arange(int(seconds * rate)) / rate
    samples = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("media")
    files = {
        "image": root / "photo.jpg",
        "png": root / "photo.png",
        "audio": root / "voice.wav",
        "silence": root / "silence.wav",
        "video": root / "clip.mp4",
        "mute_video": root / "mute.mp4",
        "text": root / "notes.txt",
    }
    assert cv2.imwrite(str(files["image"]), _picture(1))
    assert cv2.imwrite(str(files["png"]), _picture(2))
    _tone(files["audio"], 1.5)
    with wave.open(str(files["silence"]), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
    files["text"].write_text("this is not media")

    frames = root / "frames"
    frames.mkdir()
    for index in range(12):
        cv2.imwrite(str(frames / f"{index:03d}.png"), _picture(10 + index))
    encode = [ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", "6"]
    encode += ["-i", str(frames / "%03d.png")]
    video_codec = ["-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p"]
    subprocess.run([*encode, *video_codec, str(files["mute_video"])], check=True)
    with_sound = [*encode, "-i", str(files["audio"]), *video_codec, "-c:a", "aac", "-shortest"]
    subprocess.run([*with_sound, str(files["video"])], check=True)
    return files
