from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import onnxruntime as ort
import pytest
from PIL import Image

from dfd.application.scans import apply_analysis
from dfd.domain import errors
from dfd.domain.entities import Analysis, MediaType, ModalityResult, Scan, ScanStatus, Thresholds
from dfd.domain.scoring import strongest
from dfd.infrastructure.analysis import TorchMediaAnalyzer
from dfd.infrastructure.ml.cards import file_sha256, save_card
from dfd.infrastructure.ml.download import smaug_card
from dfd.infrastructure.ml.registry import ModelRegistry
from dfd.infrastructure.ml.smaug import CROP, SmaugDetector, image_views, sigmoid
from tests.conftest import CentreFace


@pytest.mark.parametrize("width,height", [(300, 400), (650, 560), (1500, 2000), (528, 528)])
def test_views_match_upstream_resize_and_crop(width: int, height: int) -> None:
    rng = np.random.default_rng(0)
    bgr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    picture = Image.fromarray(bgr[..., ::-1])
    if min(width, height) > 576:
        scale = 576 / min(width, height)
        picture = picture.resize(
            (round(width * scale), round(height * scale)), Image.Resampling.LANCZOS
        )
    elif min(width, height) < 528:
        scale = 528 / min(width, height)
        picture = picture.resize(
            (math.ceil(width * scale), math.ceil(height * scale)), Image.Resampling.BICUBIC
        )
    w, h = picture.size
    cx, cy = (w - 528) // 2, (h - 528) // 2
    spots = ((0, cy), (cx, cy), (w - 528, cy)) if w >= h else ((cx, 0), (cx, cy), (cx, h - 528))
    actual = list(image_views(bgr))
    assert len(actual) == 3
    for view, (x, y) in zip(actual, spots, strict=True):
        expected = np.asarray(picture.crop((x, y, x + 528, y + 528)))
        assert view.shape == (1, 3, CROP, CROP) and view.dtype == np.float32
        assert view.flags.c_contiguous
        np.testing.assert_allclose(view[0].transpose(1, 2, 0), expected / 255, atol=1e-7)


def test_smaug_averages_logits_not_probabilities() -> None:
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name="pixels")]
    session.run.side_effect = [np.array([[-2.0]]), np.array([[1.0]]), np.array([[4.0]])]
    detector = SmaugDetector(session, smaug_card())
    score = detector.predict(np.zeros((528, 528, 3), dtype=np.uint8))
    assert score == pytest.approx(sigmoid(1.0))
    assert session.run.call_count == 3
    assert all(call.args[1]["pixels"].shape[0] == 1 for call in session.run.call_args_list)


def test_invalid_logits_are_not_treated_as_real() -> None:
    assert sigmoid(-10000) == 0.0 and sigmoid(10000) == 1.0
    with pytest.raises(ValueError, match="non-finite"):
        sigmoid(float("nan"))
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name="pixels")]
    session.run.return_value = [np.zeros(2)]
    with pytest.raises(ValueError, match="one logit"):
        SmaugDetector(session, smaug_card()).predict(np.zeros((528, 528, 3), dtype=np.uint8))


def test_load_missing_model_is_a_domain_error(tmp_path: Path) -> None:
    with pytest.raises(errors.ModelUnavailable):
        SmaugDetector.load(tmp_path)


@pytest.mark.parametrize(
    "face,ai,expected",
    [
        (0.01, 0.999, "fake"),
        (0.99, 0.001, "fake"),
        (0.1, 0.1, "real"),
        (0.5, 0.01, "suspicious"),
        (None, 0.99, "fake"),
        (None, None, "inconclusive"),
    ],
)
def test_separate_image_paths_keep_their_own_verdicts(
    face: float | None, ai: float | None, expected: str
) -> None:
    scan = Scan(
        "s",
        1,
        "a.jpg",
        "s.jpg",
        "a" * 64,
        100,
        MediaType.IMAGE,
        ScanStatus.QUEUED,
        datetime.now(UTC),
    )
    analysis = Analysis(
        visual=ModalityResult(face, Thresholds(0.2, 0.8), "face") if face is not None else None,
        synthetic=ModalityResult(ai, Thresholds(0.5, 0.5), "smaug", True)
        if ai is not None
        else None,
        provenance=["ai_declared"],
    )
    apply_analysis(scan, analysis)
    assert scan.verdict == expected
    assert scan.prob_fake == max([p for p in (face, ai) if p is not None], default=None)
    assert scan.details["provenance"] == ["ai_declared"]
    if ai is not None:
        assert scan.details["synthetic"]["prob"] == ai
    # Metadata alone does not change an inconclusive verdict to fake.
    assert strongest(None, None) is None


def test_cannot_compare_raw_scores_across_different_thresholds() -> None:
    scan = Scan(
        "s",
        1,
        "a.jpg",
        "s.jpg",
        "a" * 64,
        100,
        MediaType.IMAGE,
        ScanStatus.QUEUED,
        datetime.now(UTC),
    )
    analysis = Analysis(
        visual=ModalityResult(0.1, Thresholds(0.01, 0.05), "face"),
        synthetic=ModalityResult(0.49, Thresholds(0.5, 0.5), "smaug", True),
    )
    apply_analysis(scan, analysis)
    assert scan.verdict == "fake"  # face path is fake even though AI score is higher
    assert scan.details["visual"]["verdict"] == "fake"
    assert scan.details["synthetic"]["verdict"] == "real"


def test_no_face_image_still_uses_smaug(tmp_path: Path) -> None:
    path = tmp_path / "landscape.png"
    cv2.imwrite(str(path), np.zeros((150, 250, 3), dtype=np.uint8))
    registry = Mock(spec=ModelRegistry)
    registry.synthetic.return_value.card = smaug_card()
    registry.synthetic.return_value.predict.return_value = 0.99
    analyzer = TorchMediaAnalyzer(registry, CentreFace())
    progress = Mock()
    result = analyzer.analyze(path, MediaType.IMAGE, tmp_path / "out", progress)
    assert result.synthetic is not None and result.synthetic.prob_fake == 0.99
    assert result.visual is None and result.frames == []
    assert "no_face_found" in result.notes and "synthetic_heatmap" in result.notes
    registry.visual.assert_not_called()
    assert (tmp_path / "out" / "overview.jpg").is_file()


def test_smaug_failure_does_not_crash_existing_face_path(
    tmp_path: Path, weights_dir: Path, media: dict[str, Path]
) -> None:
    registry = ModelRegistry(weights_dir, "cpu")
    registry._synthetic = Mock()  # a broken inference session, not a missing model
    registry._synthetic.predict.side_effect = RuntimeError("bad ONNX output")
    analyzer = TorchMediaAnalyzer(registry, CentreFace())
    result = analyzer.analyze(media["image"], MediaType.IMAGE, tmp_path / "out", Mock())
    assert result.visual is not None and result.synthetic is None
    assert "synthetic_failed" in result.notes and result.frames


def test_smaug_works_without_face_model(tmp_path: Path, media: dict[str, Path]) -> None:
    registry = Mock(spec=ModelRegistry)
    registry.synthetic.return_value.card = smaug_card()
    registry.synthetic.return_value.predict.return_value = 0.99
    registry.visual.side_effect = errors.ModelUnavailable(kind="visual")
    result = TorchMediaAnalyzer(registry, CentreFace()).analyze(
        media["image"], MediaType.IMAGE, tmp_path / "out", Mock()
    )
    assert result.synthetic is not None and "visual_model_unavailable" in result.notes


def test_registry_checks_hash_loads_onnx_once_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "synthetic"
    folder.mkdir()
    weights = folder / "model.onnx"
    weights.write_bytes(b"onnx-placeholder")
    card = replace(smaug_card(), sha256=file_sha256(weights))
    save_card(folder, card)
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name="pixels")]
    load_session = Mock(return_value=session)
    monkeypatch.setattr(ort, "InferenceSession", load_session)
    registry = ModelRegistry(tmp_path)
    assert registry.status()["synthetic"]["available"] is True
    load_session.assert_not_called()
    assert registry.synthetic() is registry.synthetic()
    assert load_session.call_count == 1
    assert load_session.call_args.kwargs["providers"] == ["CPUExecutionProvider"]
    weights.write_bytes(b"tampered")
    with pytest.raises(errors.ModelUnavailable):
        SmaugDetector.load(folder)
    # Missing synthetic cards raise a domain error without making a network call.
    with pytest.raises(errors.ModelUnavailable):
        ModelRegistry(tmp_path / "empty").synthetic()
