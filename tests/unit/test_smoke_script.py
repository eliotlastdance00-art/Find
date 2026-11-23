"""Keep the Docker smoke check aligned with optional whole-image inference."""

from __future__ import annotations

from typing import Any

import pytest
from scripts import smoke_test as S


def image_result(verdict: str = "real", probability: float = 0.1) -> dict[str, Any]:
    return {
        "status": "done",
        "verdict": verdict,
        "prob_fake": probability,
        "details": {
            "visual": None,
            "synthetic": {"verdict": verdict, "prob": probability},
            "notes": ["no_face_found", "synthetic_score"],
        },
    }


@pytest.mark.parametrize("verdict,probability", [("real", 0.1), ("suspicious", 0.5), ("fake", 0.9)])
def test_smoke_does_not_assign_ground_truth_to_a_generated_gradient(
    verdict: str, probability: float
) -> None:
    S.check_no_face_image(image_result(verdict, probability), synthetic_available=True)


def test_no_face_is_inconclusive_without_whole_image_model() -> None:
    image = image_result()
    image["verdict"] = "inconclusive"
    image["prob_fake"] = None
    image["details"]["synthetic"] = None
    image["details"]["notes"] = ["no_face_found", "synthetic_model_unavailable"]
    S.check_no_face_image(image, synthetic_available=False)
    with pytest.raises(AssertionError, match="did not return a score"):
        S.check_no_face_image(image, synthetic_available=True)


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan")])
def test_smoke_still_rejects_invalid_whole_image_scores(probability: float) -> None:
    with pytest.raises(AssertionError):
        S.check_no_face_image(image_result(probability=probability), synthetic_available=True)


def test_smoke_requires_the_whole_image_result_to_reach_the_headline() -> None:
    image = image_result()
    image["verdict"] = "inconclusive"
    with pytest.raises(AssertionError):
        S.check_no_face_image(image, synthetic_available=True)
