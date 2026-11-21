"""Pure helpers of the audio fine-tuning script (no audio files, no ffmpeg, no GPU)."""

import random
from pathlib import Path

import numpy as np
import pytest
from training import train_audio as T


def test_fit_length_cuts_and_repeats() -> None:
    wave = np.arange(5, dtype=np.float32)
    assert T.fit_length(wave, 3).tolist() == [0, 1, 2]
    assert T.fit_length(wave, 12).tolist() == [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1]


def test_random_crop_is_seeded_and_in_range() -> None:
    wave = np.arange(100, dtype=np.float32)
    first = T.random_crop(wave, 10, random.Random(3))
    assert first.tolist() == T.random_crop(wave, 10, random.Random(3)).tolist()
    assert first.size == 10 and first[-1] - first[0] == 9
    assert T.random_crop(wave[:4], 10, random.Random(0)).size == 10


def test_set_peak_and_silence() -> None:
    wave = np.asarray([0.1, -0.2, 0.05], dtype=np.float32)
    assert float(np.abs(T.set_peak(wave, 0.5)).max()) == pytest.approx(0.5)
    silent = np.zeros(4, dtype=np.float32)
    assert T.set_peak(silent, 0.5) is silent


def test_augment_gives_every_clip_a_level_in_range() -> None:
    wave = (0.3 * np.sin(np.arange(1600) / 5)).astype(np.float32)
    peaks = [
        float(np.abs(T.augment(wave, random.Random(i), (), codec_p=1.0, noise_p=0.5)).max())
        for i in range(40)
    ]
    assert min(peaks) >= 0.02 - 1e-6 and max(peaks) <= 0.99 + 1e-6
    assert max(peaks) / min(peaks) > 5  # really random, not one fixed level


def test_lr_schedule() -> None:
    assert T.lr_at(0.0, 1e-4, 5e-6) == pytest.approx(1e-4)
    assert T.lr_at(1.0, 1e-4, 5e-6) == pytest.approx(5e-6)
    assert T.lr_at(7.0, 1e-4, 5e-6) == pytest.approx(5e-6)
    assert 5e-6 < T.lr_at(0.5, 1e-4, 5e-6) < 1e-4


def items(spec: dict[str, tuple[int, int]]) -> list[T.Item]:
    return [
        (f"{name}{i}", Path(f"{name}/{i}.flac"), label, name)
        for name, (label, count) in spec.items()
        for i in range(count)
    ]


def test_buckets_balance_classes_and_generators() -> None:
    tk = items({"real_cv": (0, 30), "tts_mms": (1, 50), "rs_dac": (1, 5)})
    la = items({"-": (0, 10), "A01": (1, 40)})
    buckets = T.make_buckets(tk, la, tk_share=0.6)
    assert [b.name for b in buckets] == ["tk_real", "tk_fake", "la_real", "la_fake"]
    assert sum(b.weight for b in buckets) == pytest.approx(1.0)
    assert sum(b.weight for b in buckets if b.label) == pytest.approx(0.5)
    fake = buckets[1]
    assert sorted(len(group) for group in fake.groups) == [5, 50]  # drawn evenly per generator
    assert fake.codec_p > buckets[0].codec_p
    assert [b.name for b in T.make_buckets(tk, [], 0.6)] == ["tk_real", "tk_fake"]


def test_breakdown_and_held_out_split() -> None:
    held = T.HELD_OUT[0]
    clips = items({"real_ts": (0, 4), "tts_mms": (1, 4), held: (1, 2)})
    probs = np.asarray([0.01, 0.02, 0.03, 0.6, 0.99, 0.98, 0.97, 0.4, 0.95, 0.05])
    report = T.breakdown(clips, probs, (0.1, 0.9))
    assert report["real"]["real_ts"] == {"n": 4, "as_real": 0.75, "as_fake": 0.0}
    assert (
        report["fake"]["tts_mms"]["as_fake"] == 0.75 and not report["fake"]["tts_mms"]["held_out"]
    )
    unseen_fake = report["fake"][held]
    assert unseen_fake["held_out"] and unseen_fake["n"] == 2
    assert unseen_fake["as_fake"] == 0.5 and unseen_fake["as_real"] == 0.5
    logits = [[float(p)] for p in probs]
    seen, _ = T.keep(clips, logits, held_out=False)
    unseen, unseen_logits = T.keep(clips, logits, held_out=True)
    assert {c[3] for c in seen} == {"real_ts", "tts_mms"}
    assert {c[3] for c in unseen} == {"real_ts", held} and len(unseen_logits) == 6


def test_subset_is_seeded() -> None:
    clips = items({"a": (0, 20)})
    assert T.subset(clips, 0) is clips
    assert T.subset(clips, 5, seed=1) == T.subset(clips, 5, seed=1)
    assert len(T.subset(clips, 5)) == 5
