"""Pure decision logic: score aggregation, three-way verdicts and modality fusion.

The same aggregation is used when thresholds are calibrated (training/) and when the
application scores a file, so the two can never drift apart.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from dfd.domain.entities import MediaType, Thresholds, Verdict

TOP_FRACTION = 0.25
_SEVERITY = {Verdict.REAL: 0, Verdict.SUSPICIOUS: 1, Verdict.FAKE: 2}


def aggregate_scores(probs: Sequence[float], top_fraction: float = TOP_FRACTION) -> float:
    """Collapse per-frame (or per-window) probabilities into one score.

    Average of the overall mean and the mean of the highest ``top_fraction`` of values:
    a clip that is manipulated only in part still scores high, while a single noisy
    frame cannot dominate.
    """
    if not probs:
        raise ValueError("cannot aggregate an empty sequence")
    values = sorted((float(p) for p in probs), reverse=True)
    k = max(1, math.ceil(len(values) * top_fraction))
    mean_all = sum(values) / len(values)
    mean_top = sum(values[:k]) / k
    return 0.5 * mean_all + 0.5 * mean_top


def classify(prob_fake: float, thresholds: Thresholds) -> Verdict:
    if prob_fake >= thresholds.fake_min:
        return Verdict.FAKE
    if prob_fake <= thresholds.real_max:
        return Verdict.REAL
    return Verdict.SUSPICIOUS


def cap(verdict: Verdict, limit: Verdict | None) -> Verdict:
    """Never report more than ``limit``.

    A model card can carry such a limit when its model is known to be unreliable in some
    setting; a detector that cannot be trusted to say "fake" may then say "suspicious" at most.
    """
    if limit is None or _SEVERITY[verdict] <= _SEVERITY[limit]:
        return verdict
    return limit


def strongest(*verdicts: Verdict | None) -> Verdict | None:
    """Independent detectors keep their own thresholds; no probability averaging.

    A low face-swap score cannot cancel a strong AI-generation finding (or vice
    versa). The combined false-alarm rate still needs independent measurement.
    """
    present = [v for v in verdicts if v is not None]
    return max(present, key=_SEVERITY.__getitem__) if present else None


def fuse(media_type: MediaType, visual: Verdict | None, audio: Verdict | None) -> Verdict:
    """Combine per-modality verdicts into the final one.

    For a video the picture is the primary evidence. Its sound track is often music or
    noise, on which a speech anti-spoofing model is unreliable, so audio alone can raise
    the verdict to "suspicious" but never to "fake".
    """
    if visual is None and audio is None:
        return Verdict.INCONCLUSIVE
    if visual is None:
        assert audio is not None
        if media_type is MediaType.VIDEO and audio is Verdict.FAKE:
            return Verdict.SUSPICIOUS
        return audio
    if audio is None:
        return visual
    capped_audio = Verdict.SUSPICIOUS if audio is Verdict.FAKE else audio
    return max(visual, capped_audio, key=_SEVERITY.__getitem__)


def headline_probability(
    visual_prob: float | None, audio_prob: float | None, media_type: MediaType
) -> float | None:
    """The single percentage shown to the user: the primary modality's probability."""
    if media_type is MediaType.AUDIO:
        return audio_prob
    return visual_prob if visual_prob is not None else audio_prob
