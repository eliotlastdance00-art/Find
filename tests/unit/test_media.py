from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from dfd.domain import errors
from dfd.domain.entities import MediaType
from dfd.infrastructure.media import audio as pcm
from dfd.infrastructure.media.faces import Face, FaceDetector, crop_face
from dfd.infrastructure.media.ffmpeg import extract_audio, parse_probe, probe
from dfd.infrastructure.media.frames import pick_indices, read_image, sample_frames
from dfd.infrastructure.media.inspect import FileInspector, sniff
from dfd.infrastructure.ml.gradcam import GradCAM, find_target_layer, overlay_heatmap
from dfd.infrastructure.ml.visual import build_backbone


def test_pick_indices_are_spread_unique_and_in_range() -> None:
    assert pick_indices(10, 20) == list(range(10))
    picked = pick_indices(1000, 16)
    assert len(picked) == len(set(picked)) == 16
    assert picked == sorted(picked)
    assert picked[0] >= 0 and picked[-1] < 1000
    assert pick_indices(0, 5) == []


def test_windows_pads_short_clips_by_repetition() -> None:
    samples = np.arange(100, dtype=np.float32)
    batch, spans = pcm.windows(samples, 100, 250, 125)
    assert batch.shape == (1, 250)
    assert np.array_equal(batch[0, 100:200], samples)
    assert spans == [(0.0, 1.0)]


def test_windows_cover_the_whole_clip() -> None:
    samples = np.arange(1000, dtype=np.float32)
    batch, spans = pcm.windows(samples, 100, 400, 200)
    assert batch.shape == (4, 400)
    assert batch[-1, -1] == 999  # last window is right-aligned
    assert spans[0] == (0.0, 4.0) and spans[-1] == (6.0, 10.0)
    with pytest.raises(ValueError):
        pcm.windows(np.zeros(0, dtype=np.float32), 100, 400, 200)


def test_silence_detection() -> None:
    assert pcm.is_silent(np.zeros(1000, dtype=np.float32))
    assert not pcm.is_silent(np.full(1000, 0.2, dtype=np.float32))


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\xff\xd8\xff\xe0" + b"\0" * 12, ("image", "jpeg")),
        (b"\x89PNG\r\n\x1a\n" + b"\0" * 8, ("image", "png")),
        (b"RIFF\0\0\0\0WEBPVP8 ", ("image", "webp")),
        (b"RIFF\0\0\0\0WAVEfmt ", ("av", "wav")),
        (b"\0\0\0\x20ftypisom\0\0\0\0", ("av", "mp4")),
        (b"fLaC" + b"\0" * 12, ("av", "flac")),
        (b"MZ\x90\0" + b"\0" * 12, None),
        (b"<html><script>", None),
    ],
)
def test_sniff_goes_by_content_not_extension(
    header: bytes, expected: tuple[str, str] | None
) -> None:
    assert sniff(header) == expected


def test_parse_probe_reads_ffmpeg_banner() -> None:
    banner = """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'clip.mp4':
  Duration: 00:01:02.50, start: 0.000000, bitrate: 1205 kb/s
  Stream #0:0[0x1](und): Video: h264 (High), yuv420p(progressive), 1280x720 [SAR 1:1], 25 fps
  Stream #0:1[0x2](und): Audio: aac (LC), 44100 Hz, stereo, fltp, 128 kb/s
"""
    info = parse_probe(banner)
    assert info.duration_s == pytest.approx(62.5)
    assert (info.width, info.height) == (1280, 720)
    assert info.has_video and info.has_audio


def test_inspector_classifies_real_files(media: dict[str, Path]) -> None:
    inspector = FileInspector()
    image = inspector.inspect(media["image"])
    assert image.media_type is MediaType.IMAGE and (image.width, image.height) == (320, 240)
    video = inspector.inspect(media["video"])
    assert video.media_type is MediaType.VIDEO and video.has_audio
    assert video.duration_s == pytest.approx(2.0, abs=0.6)
    assert inspector.inspect(media["mute_video"]).has_audio is False
    assert inspector.inspect(media["audio"]).media_type is MediaType.AUDIO
    with pytest.raises(errors.UnsupportedMedia):
        inspector.inspect(media["text"])


def test_inspector_rejects_truncated_image(tmp_path: Path, media: dict[str, Path]) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(media["image"].read_bytes()[:40])
    with pytest.raises(errors.CorruptMedia):
        FileInspector().inspect(broken)


def test_sample_frames_and_read_image(media: dict[str, Path]) -> None:
    frames = list(sample_frames(media["video"], 4))
    assert len(frames) == 4
    assert frames[0].image.shape == (240, 320, 3)
    assert [f.index for f in frames] == sorted({f.index for f in frames})
    image = read_image(media["png"])
    assert image is not None and image.shape == (240, 320, 3)
    assert read_image(media["text"]) is None


def test_extract_audio_resamples_to_mono_16k(tmp_path: Path, media: dict[str, Path]) -> None:
    target = tmp_path / "out.wav"
    extract_audio(media["video"], target, 16000, 60.0)
    samples, rate = pcm.read_wav(target)
    assert rate == 16000
    assert samples.ndim == 1 and 16000 <= samples.size <= 16000 * 3
    assert probe(target).has_audio
    with pytest.raises(errors.CorruptMedia):
        extract_audio(media["mute_video"], tmp_path / "none.wav", 16000, 60.0)


def test_yunet_loads_and_finds_nothing_in_noise() -> None:
    noise = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    assert FaceDetector().detect(noise) == []


def test_crop_face_is_square_and_handles_borders() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[:, :100] = 255
    crop = crop_face(image, Face(-10, -10, 40, 60, 0.9), margin=1.3, size=64)
    assert crop.shape == (64, 64, 3)
    inner = crop_face(image, Face(80, 30, 40, 40, 0.9), margin=1.0)
    assert inner.shape == (40, 40, 3)
    assert inner[:, :20].mean() == 255 and inner[:, 20:].mean() == 0


def test_gradcam_returns_normalised_maps_and_removes_hooks() -> None:
    torch.manual_seed(0)
    model = build_backbone("test_efficientnet").eval()
    layer = find_target_layer(model)
    batch = torch.rand(2, 3, 96, 96)
    with GradCAM(model, layer) as cam:
        logits, maps = cam(batch)
    assert logits.shape == (2,)
    assert maps.shape == (2, 96, 96)
    assert float(maps.min()) >= 0.0 and float(maps.max()) <= 1.0
    assert len(layer._forward_hooks) == 0
    with torch.inference_mode():
        assert torch.allclose(model(batch).reshape(-1), logits, atol=1e-5)

    heat = maps[0].numpy()
    image = np.full((96, 96, 3), 128, dtype=np.uint8)
    blended = overlay_heatmap(image, heat)
    assert blended.shape == image.shape and blended.dtype == np.uint8
    assert np.array_equal(overlay_heatmap(image, np.zeros((96, 96), dtype=np.float32)), image)


def test_gradcam_target_layer_lookup() -> None:
    model = build_backbone("test_efficientnet")
    assert find_target_layer(model, "conv_head") is model.conv_head
    with pytest.raises(ValueError):
        find_target_layer(torch.nn.Linear(2, 1))
