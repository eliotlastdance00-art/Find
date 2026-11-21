from __future__ import annotations

import io
from pathlib import Path

import pytest

from dfd.domain import errors
from dfd.domain.entities import Thresholds, Verdict
from dfd.infrastructure.ml.cards import (
    IMAGENET_MEAN,
    ModelCard,
    file_sha256,
    load_card,
    save_card,
    verify_weights,
)
from dfd.infrastructure.ml.registry import ModelRegistry
from dfd.infrastructure.storage import LocalFileStorage


def _card(weights: Path) -> ModelCard:
    return ModelCard(
        name="m",
        version="1",
        kind="visual",
        arch="test_efficientnet",
        weights_file=weights.name,
        sha256=file_sha256(weights),
        thresholds={"image": Thresholds(0.2, 0.8)},
        temperature=1.7,
        input_size=96,
    )


def test_card_roundtrip(tmp_path: Path) -> None:
    weights = tmp_path / "w.pth"
    weights.write_bytes(b"abc")
    save_card(tmp_path, _card(weights))
    loaded = load_card(tmp_path)
    assert loaded == _card(weights)
    assert loaded.thresholds_for("image") == Thresholds(0.2, 0.8)
    assert loaded.label == "m 1"


def test_card_defaults_apply_when_fields_are_missing() -> None:
    card = ModelCard.from_json(
        {
            "name": "m",
            "version": "1",
            "kind": "audio",
            "arch": "AASIST",
            "weights_file": "w.pth",
            "sha256": "",
            "thresholds": {"audio": {"real_max": 0.3, "fake_min": 0.7}},
        }
    )
    assert card.mean == IMAGENET_MEAN
    assert card.temperature == 1.0
    assert card.provisional is False


def test_card_verdict_limit_roundtrips_and_is_validated(tmp_path: Path) -> None:
    weights = tmp_path / "w.pth"
    weights.write_bytes(b"weights")
    data = _card(weights).to_json()
    assert "max_verdict" not in data  # absent unless a limit is set
    limited = ModelCard.from_json({**data, "max_verdict": "suspicious"})
    assert limited.max_verdict is Verdict.SUSPICIOUS
    assert ModelCard.from_json(limited.to_json()) == limited
    with pytest.raises(ValueError, match="max_verdict"):
        ModelCard.from_json({**data, "max_verdict": "fake"})


def test_card_requires_thresholds() -> None:
    with pytest.raises(ValueError):
        ModelCard.from_json(
            {"name": "m", "version": "1", "kind": "audio", "arch": "x", "weights_file": "w",
             "sha256": "", "thresholds": {}}
        )  # fmt: skip


def test_verify_weights_detects_tampering(tmp_path: Path) -> None:
    weights = tmp_path / "w.pth"
    weights.write_bytes(b"abc")
    card = _card(weights)
    assert verify_weights(tmp_path, card) == weights
    weights.write_bytes(b"abd")
    with pytest.raises(ValueError, match="checksum"):
        verify_weights(tmp_path, card)
    weights.unlink()
    with pytest.raises(FileNotFoundError):
        verify_weights(tmp_path, card)


def test_registry_reports_missing_models(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    assert registry.status() == {"visual": {"available": False}, "audio": {"available": False}}
    with pytest.raises(errors.ModelUnavailable):
        registry.visual()


def test_registry_loads_and_caches(weights_dir: Path) -> None:
    registry = ModelRegistry(weights_dir, "cpu")
    status = registry.status()
    assert status["visual"]["available"] and status["audio"]["available"]
    assert status["visual"]["provisional"] is True
    assert registry.visual() is registry.visual()


def test_storage_saves_hashes_and_sanitises_names(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "up", tmp_path / "scans")
    stored = storage.save_upload("abc123", "../../etc/pass wd.JPG", io.BytesIO(b"hello"), 100)
    assert stored.size_bytes == 5
    assert stored.sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert stored.path.parent == tmp_path / "up"
    assert stored.path.name == "abc123.jpg"
    assert stored.path.read_bytes() == b"hello"


def test_storage_enforces_size_limit_and_cleans_up(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "up", tmp_path / "scans")
    with pytest.raises(errors.FileTooLarge):
        storage.save_upload("big", "a.mp4", io.BytesIO(b"x" * 11), 10)
    assert list((tmp_path / "up").iterdir()) == []


def test_storage_artifact_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "up", tmp_path / "scans")
    folder = storage.scan_dir("abc")
    (folder / "heat_1.jpg").write_bytes(b"x")
    (tmp_path / "scans" / "secret.jpg").write_bytes(b"x")
    assert storage.artifact("abc", "heat_1.jpg") == folder / "heat_1.jpg"
    assert storage.artifact("abc", "../secret.jpg") is None
    assert storage.artifact("abc", "missing.jpg") is None
    assert storage.artifact("abc", "audio.exe") is None


def test_storage_delete_removes_everything(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "up", tmp_path / "scans")
    stored = storage.save_upload("abc", "a.png", io.BytesIO(b"x"), 10)
    folder = storage.scan_dir("abc")
    (folder / "heat_1.jpg").write_bytes(b"x")
    storage.delete_scan("abc", stored.name)
    assert not stored.path.exists()
    assert not folder.exists()
