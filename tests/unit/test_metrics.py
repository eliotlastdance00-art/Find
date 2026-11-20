from __future__ import annotations

import numpy as np
import pytest

from dfd.infrastructure.ml import metrics as M


def test_auc_of_perfect_and_inverted_rankings() -> None:
    labels = [0, 0, 1, 1]
    assert M.auc(labels, [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)
    assert M.auc(labels, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(0.0)


def test_auc_matches_pairwise_definition() -> None:
    rng = np.random.default_rng(0)
    labels = rng.integers(0, 2, 300)
    scores = rng.normal(size=300) + labels
    positives, negatives = scores[labels == 1], scores[labels == 0]
    wins = (positives[:, None] > negatives[None, :]).mean()
    assert M.auc(labels, scores) == pytest.approx(wins, abs=1e-9)


def test_auc_counts_ties_as_half() -> None:
    assert M.auc([0, 1], [0.5, 0.5]) == pytest.approx(0.5)


def test_roc_needs_both_classes() -> None:
    with pytest.raises(ValueError):
        M.auc([1, 1], [0.1, 0.9])


def test_eer_for_separable_and_overlapping_scores() -> None:
    rate, _ = M.eer([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert rate == pytest.approx(0.0)
    rate, threshold = M.eer([0, 0, 1, 1], [0.1, 0.6, 0.4, 0.9])
    assert rate == pytest.approx(0.5)
    assert 0.1 <= threshold <= 0.9


def test_accuracy() -> None:
    assert M.accuracy([0, 1, 1, 0], [0.2, 0.7, 0.4, 0.6]) == pytest.approx(0.5)


def test_decision_band_is_ordered_and_bounds_errors() -> None:
    rng = np.random.default_rng(1)
    labels = np.r_[np.zeros(2000), np.ones(2000)]
    scores = np.clip(np.r_[rng.normal(0.3, 0.12, 2000), rng.normal(0.7, 0.12, 2000)], 0, 1)
    real_max, fake_min = M.decision_band(labels, scores, max_error=0.05)
    assert 0.0 <= real_max <= fake_min <= 1.0
    rates = M.verdict_rates(labels, scores, real_max, fake_min)
    assert rates["fake"]["as_real"] <= 0.06
    assert rates["real"]["as_fake"] <= 0.06
    for group in rates.values():
        assert group["as_real"] + group["as_suspicious"] + group["as_fake"] == pytest.approx(1)


def test_fit_temperature_recovers_scale() -> None:
    rng = np.random.default_rng(2)
    true_logits = rng.normal(0, 2, 20000)
    labels = (rng.random(20000) < 1 / (1 + np.exp(-true_logits))).astype(float)
    assert M.fit_temperature(true_logits * 4.0, labels) == pytest.approx(4.0, rel=0.1)
    assert M.fit_temperature(true_logits, labels) == pytest.approx(1.0, rel=0.1)
