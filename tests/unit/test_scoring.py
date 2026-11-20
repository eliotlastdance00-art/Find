from __future__ import annotations

import pytest

from dfd.domain.entities import MediaType, Thresholds, Verdict
from dfd.domain.scoring import aggregate_scores, classify, fuse, headline_probability

BAND = Thresholds(0.3, 0.7)


def test_aggregate_single_value_is_identity() -> None:
    assert aggregate_scores([0.42]) == pytest.approx(0.42)


def test_aggregate_rewards_partially_manipulated_clips() -> None:
    mostly_clean = [0.05] * 15 + [0.95] * 5
    assert aggregate_scores(mostly_clean) > sum(mostly_clean) / len(mostly_clean)
    assert aggregate_scores(mostly_clean) == pytest.approx(0.5 * 0.275 + 0.5 * 0.95)


def test_aggregate_single_outlier_cannot_dominate() -> None:
    assert aggregate_scores([0.05] * 39 + [1.0]) < 0.3


def test_aggregate_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        aggregate_scores([])


@pytest.mark.parametrize(
    ("prob", "expected"),
    [
        (0.0, Verdict.REAL),
        (0.3, Verdict.REAL),
        (0.31, Verdict.SUSPICIOUS),
        (0.69, Verdict.SUSPICIOUS),
        (0.7, Verdict.FAKE),
        (1.0, Verdict.FAKE),
    ],
)
def test_classify_boundaries(prob: float, expected: Verdict) -> None:
    assert classify(prob, BAND) is expected


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError):
        Thresholds(0.8, 0.2)


def test_fuse_without_evidence_is_inconclusive() -> None:
    assert fuse(MediaType.VIDEO, None, None) is Verdict.INCONCLUSIVE


def test_fuse_single_modality_passes_through() -> None:
    assert fuse(MediaType.IMAGE, Verdict.FAKE, None) is Verdict.FAKE
    assert fuse(MediaType.AUDIO, None, Verdict.FAKE) is Verdict.FAKE


@pytest.mark.parametrize(
    ("visual", "audio", "expected"),
    [
        (Verdict.REAL, Verdict.REAL, Verdict.REAL),
        (Verdict.REAL, Verdict.FAKE, Verdict.SUSPICIOUS),  # audio alone never says "fake"
        (Verdict.REAL, Verdict.SUSPICIOUS, Verdict.SUSPICIOUS),
        (Verdict.SUSPICIOUS, Verdict.REAL, Verdict.SUSPICIOUS),
        (Verdict.FAKE, Verdict.REAL, Verdict.FAKE),
        (None, Verdict.FAKE, Verdict.SUSPICIOUS),
        (None, Verdict.REAL, Verdict.REAL),
    ],
)
def test_fuse_video(visual: Verdict | None, audio: Verdict, expected: Verdict) -> None:
    assert fuse(MediaType.VIDEO, visual, audio) is expected


def test_headline_probability_follows_primary_modality() -> None:
    assert headline_probability(0.2, 0.9, MediaType.VIDEO) == 0.2
    assert headline_probability(0.2, 0.9, MediaType.AUDIO) == 0.9
    assert headline_probability(None, 0.9, MediaType.VIDEO) == 0.9
    assert headline_probability(None, None, MediaType.IMAGE) is None
