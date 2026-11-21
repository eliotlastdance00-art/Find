"""Shared pieces of the Turkmen audio set builder: paths, audio I/O, splits, output sinks.

Imports only the standard library at module level, so planning and its tests need nothing
else; numpy, scipy and soundfile are loaded when audio is actually touched. Generator workers
run in separate interpreters (some inside their own virtualenv) and import this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import traceback
from collections.abc import Callable, Iterable
from math import gcd
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16_000
SPLITS = ("train", "dev", "test")
HELD_OUT = ("rs_vocos", "tts_omnivoice")  # generated for the test split only
MIN_SECONDS, MAX_SECONDS = 0.8, 20.0

Job = dict[str, Any]
Synth = Callable[[Job], tuple[Any, int]]


def out_root() -> Path:
    """Small, durable outputs (metadata, archives, logs): the kernel's output directory."""
    return Path(os.environ.get("TK_OUT", "/kaggle/working/tkset"))


def work_root() -> Path:
    """Bulky scratch space: one audio file per clip, archived per generator afterwards."""
    return Path(os.environ.get("TK_WORK", "/tmp/tkset"))


def deadline() -> float:
    """Epoch second after which a worker must not start another clip."""
    return float(os.environ.get("TK_DEADLINE", "inf"))


def stable_hash(text: str) -> int:
    return int.from_bytes(hashlib.sha1(text.encode()).digest()[:8], "big")


def split_of(group: str) -> str:
    """Deterministic 70/15/15 split of a recording group (a video or a speaker)."""
    bucket = stable_hash("split:" + group) % 100
    return "train" if bucket < 70 else "dev" if bucket < 85 else "test"


# --- audio ------------------------------------------------------------------------------


def resample(wav: Any, rate: int, target: int) -> Any:
    if rate == target:
        return wav
    from scipy.signal import resample_poly  # noqa: PLC0415

    divisor = gcd(int(rate), int(target))
    return resample_poly(wav, target // divisor, rate // divisor).astype("float32")


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg  # noqa: PLC0415

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return "ffmpeg"


def read_audio(path: str | Path) -> tuple[Any, int]:
    """Mono float32 samples and the native sample rate; falls back to FFmpeg for MP3."""
    import soundfile as sf  # noqa: PLC0415

    try:
        wav, rate = sf.read(str(path), dtype="float32", always_2d=False)
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            subprocess.run(
                [_ffmpeg(), "-v", "error", "-y", "-i", str(path), "-ac", "1", tmp.name],
                check=True,
            )
            wav, rate = sf.read(tmp.name, dtype="float32", always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav, int(rate)


def load(path: str | Path, rate: int = SAMPLE_RATE) -> Any:
    wav, native = read_audio(path)
    return resample(wav, native, rate)


def write_wav(path: str | Path, wav: Any, rate: int = SAMPLE_RATE) -> None:
    import soundfile as sf  # noqa: PLC0415

    sf.write(str(path), wav, rate, subtype="PCM_16")


# --- metadata ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[Job]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:  # a line cut off by a kill; the clip is redone
            continue
    return rows


def load_plan(name: str) -> list[Job]:
    path = out_root() / "plan" / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else []


class Sink:
    """Writes one generator's clips as 16 kHz FLAC and records each one immediately.

    A record is appended and flushed per clip, so a killed worker loses at most the clip it was
    working on and a restarted worker skips everything already listed in ``done``.
    """

    def __init__(self, name: str, kind: str, model: str, label: int = 1) -> None:
        self.name, self.kind, self.model, self.label = name, kind, model, label
        self.dir = work_root() / "audio" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = out_root() / "meta" / f"{name}.jsonl"
        self.meta.parent.mkdir(parents=True, exist_ok=True)
        self.done = {row["id"] for row in read_jsonl(self.meta)}
        self.rejected = 0
        self.started = time.time()
        self.audio_seconds = 0.0

    def save(self, job: Job, wav: Any, rate: int, **extra: Any) -> bool:
        """Store one clip; returns False (and stores nothing) when the audio is unusable."""
        import numpy as np  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415

        wav = np.asarray(wav, dtype="float32").reshape(-1)
        if wav.size == 0 or not np.isfinite(wav).all():
            self.rejected += 1
            return False
        wav = resample(wav, int(rate), SAMPLE_RATE)
        peak = float(np.abs(wav).max())
        rms = float(np.sqrt(np.mean(wav.astype("float64") ** 2)))
        seconds = wav.size / SAMPLE_RATE
        if not MIN_SECONDS <= seconds <= MAX_SECONDS or rms < 1e-4:
            self.rejected += 1
            return False
        if peak > 0.99:  # several generators overshoot full scale; never store clipped audio
            wav = wav / peak * 0.99
        file = f"{self.name}/{job['id']}.flac"
        sf.write(str(work_root() / "audio" / file), wav, SAMPLE_RATE, subtype="PCM_16")
        row = {
            "id": job["id"],
            "file": file,
            "label": self.label,
            "generator": self.name,
            "kind": self.kind,
            "source": job["source"],
            "group": job["group"],
            "split": job["split"],
            "parent": job.get("parent", ""),
            "ref_group": job.get("ref_group", ""),
            "duration": round(seconds, 3),
            "native_sr": int(rate),
            "rms": round(rms, 5),
            "peak": round(peak, 4),
            "text": job.get("text", ""),
            **extra,
        }
        with self.meta.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.done.add(job["id"])
        self.audio_seconds += seconds
        return True

    def summary(self) -> str:
        elapsed = time.time() - self.started
        rtf = elapsed / self.audio_seconds if self.audio_seconds else float("nan")
        return f"{len(self.done)} clips, {self.rejected} rejected, {elapsed:.0f} s, RTF {rtf:.3f}"


def run_generator(
    sink: Sink,
    jobs: Iterable[Job],
    synth: Synth,
    every: int = 50,
    max_failures: int = 25,
) -> None:
    """Feed ``jobs`` through ``synth``; one bad clip is skipped, a broken generator is stopped."""
    todo = [job for job in jobs if job["id"] not in sink.done]
    print(f"[{sink.name}] {len(todo)} to do, {len(sink.done)} already done", flush=True)
    failures = 0
    for index, job in enumerate(todo, 1):
        if time.time() > deadline():
            print(f"[{sink.name}] time budget reached after {index - 1} clips", flush=True)
            break
        try:
            wav, rate = synth(job)
            if sink.save(job, wav, rate, **job.get("params", {})):
                failures = 0
        except Exception:
            failures += 1
            print(f"[{sink.name}] {job['id']} failed:\n{traceback.format_exc()[-800:]}", flush=True)
            if failures >= max_failures:
                raise RuntimeError(f"{sink.name}: {failures} failures in a row") from None
        if index % every == 0:
            print(f"[{sink.name}] {index}/{len(todo)}: {sink.summary()}", flush=True)
    print(f"[{sink.name}] finished: {sink.summary()}", flush=True)


def guarded(name: str, fn: Callable[[], None]) -> bool:
    """Run one generator; a failure is reported and never takes the next generator down."""
    try:
        fn()
        return True
    except Exception:
        print(f"[{name}] FAILED\n{traceback.format_exc()[-2500:]}", flush=True)
        return False


def generate(name: str, kind: str, model: str, jobs: Iterable[Job], synth: Synth) -> bool:
    """Run one generator over its jobs; False when the generator itself broke."""
    return guarded(name, lambda: run_generator(Sink(name, kind, model), jobs, synth))
