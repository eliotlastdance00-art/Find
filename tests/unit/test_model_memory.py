from __future__ import annotations

from unittest.mock import Mock

import pytest
import torch

from dfd.infrastructure.ml import memory
from dfd.infrastructure.ml.gradcam import GradCAM


def test_trim_is_optional_on_non_glibc_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.sys, "platform", "darwin")
    assert memory._trim_function() is None
    monkeypatch.setattr(memory.sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", Mock(side_effect=OSError("not glibc")))
    assert memory._trim_function() is None


def test_releasing_unused_memory_keeps_models_but_collects_temporaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect, trim = Mock(), Mock()
    monkeypatch.setattr(memory.gc, "collect", collect)
    monkeypatch.setattr(memory, "_TRIM", trim)
    memory.release_unused_memory()
    collect.assert_called_once()
    trim.assert_called_once_with(0)
    monkeypatch.setattr(memory, "_TRIM", None)
    memory.release_unused_memory()
    assert collect.call_count == 2


def test_gradcam_does_not_retain_parameter_gradients() -> None:
    model = torch.nn.Sequential(
        torch.nn.Conv2d(3, 2, 1),
        torch.nn.AdaptiveAvgPool2d(1),
        torch.nn.Flatten(),
        torch.nn.Linear(2, 1),
    )
    with GradCAM(model, model[0]) as cam:
        logits, heatmap = cam(torch.ones(1, 3, 16, 16))
        assert logits.shape == (1,) and heatmap.shape == (1, 16, 16)
        assert any(parameter.grad is not None for parameter in model.parameters())
    assert all(parameter.grad is None for parameter in model.parameters())
