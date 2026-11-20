"""Binary classification metrics in plain NumPy (label 1 = fake, higher score = more fake)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


def roc_curve(labels: ArrayLike, scores: ArrayLike) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Return (fpr, tpr, thresholds), thresholds descending; a sample is positive if score >= t."""
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    positives, negatives = float(y.sum()), float((1 - y).sum())
    if positives == 0 or negatives == 0:
        raise ValueError("ROC needs both classes")
    order = np.argsort(-s, kind="mergesort")
    y, s = y[order], s[order]
    distinct = np.r_[np.where(np.diff(s))[0], y.size - 1]
    tpr = np.cumsum(y)[distinct] / positives
    fpr = np.cumsum(1 - y)[distinct] / negatives
    return np.r_[0.0, fpr], np.r_[0.0, tpr], np.r_[np.inf, s[distinct]]


def auc(labels: ArrayLike, scores: ArrayLike) -> float:
    fpr, tpr, _ = roc_curve(labels, scores)
    return float(np.sum(np.diff(fpr) * (tpr[1:] + tpr[:-1]) / 2.0))


def eer(labels: ArrayLike, scores: ArrayLike) -> tuple[float, float]:
    """Equal error rate and the threshold where FPR and FNR cross."""
    fpr, tpr, thresholds = roc_curve(labels, scores)
    fnr = 1.0 - tpr
    i = int(np.argmin(np.abs(fnr - fpr)))
    return float((fpr[i] + fnr[i]) / 2.0), float(thresholds[i])


def accuracy(labels: ArrayLike, scores: ArrayLike, threshold: float = 0.5) -> float:
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    return float(np.mean((s >= threshold) == (y > 0.5)))


def decision_band(
    labels: ArrayLike, scores: ArrayLike, max_error: float = 0.05
) -> tuple[float, float]:
    """Thresholds (real_max, fake_min) for the three-way verdict.

    ``a`` is the score below which only ``max_error`` of fakes fall; ``b`` is the score above
    which only ``max_error`` of real samples lie. Everything between them is "suspicious":
    with a well separated model that is the empty gap between the classes, with a weak one
    it is the region where they overlap.
    """
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    a = float(np.quantile(s[y > 0.5], max_error))
    b = float(np.quantile(s[y <= 0.5], 1.0 - max_error))
    low, high = min(a, b), max(a, b)
    return float(np.clip(low, 0.0, 1.0)), float(np.clip(high, 0.0, 1.0))


def fit_temperature(logits: ArrayLike, labels: ArrayLike) -> float:
    """Temperature T minimising the NLL of sigmoid(logit / T) (golden-section search)."""
    z = np.asarray(logits, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)

    def nll(log_t: float) -> float:
        scaled = z / np.exp(log_t)
        return float(np.mean(np.logaddexp(0.0, scaled) - y * scaled))

    low, high = np.log(0.05), np.log(20.0)
    ratio = (np.sqrt(5.0) - 1.0) / 2.0
    c, d = high - ratio * (high - low), low + ratio * (high - low)
    for _ in range(80):
        if nll(c) < nll(d):
            high = d
        else:
            low = c
        c, d = high - ratio * (high - low), low + ratio * (high - low)
    return float(np.exp((low + high) / 2.0))


def verdict_rates(
    labels: ArrayLike, scores: ArrayLike, real_max: float, fake_min: float
) -> dict[str, dict[str, float]]:
    """Share of real and of fake samples that land in each of the three verdicts."""
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    out: dict[str, dict[str, float]] = {}
    for name, mask in (("real", y <= 0.5), ("fake", y > 0.5)):
        part = s[mask]
        out[name] = {
            "as_real": float(np.mean(part <= real_max)),
            "as_suspicious": float(np.mean((part > real_max) & (part < fake_min))),
            "as_fake": float(np.mean(part >= fake_min)),
            "count": float(part.size),
        }
    return out
