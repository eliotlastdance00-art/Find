"""FaceForensics++ discovery, official video-level splits and face extraction."""

from __future__ import annotations

import csv
import json
import multiprocessing as mp
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from dfd.infrastructure.media.faces import FaceDetector, crop_face
from dfd.infrastructure.media.frames import sample_frames

SPLITS_DIR = Path(__file__).parent / "splits"
REAL = "original"
EXCLUDED_METHODS = {"DeepFakeDetection", "csv"}


@dataclass(frozen=True, slots=True)
class Video:
    path: str
    method: str
    stem: str
    label: int
    split: str

    @property
    def key(self) -> str:
        return f"{self.method}/{self.stem}"


@dataclass(frozen=True, slots=True)
class FaceRow:
    file: str
    label: int
    method: str
    video: str
    split: str


def find_root(search: Path) -> Path:
    """Locate the directory that contains ``original/*.mp4`` somewhere under ``search``."""
    for candidate in [search, *sorted(p for p in search.rglob("*") if p.is_dir())]:
        if (candidate / REAL).is_dir() and any((candidate / REAL).glob("*.mp4")):
            return candidate
    raise FileNotFoundError(f"no FaceForensics++ layout found under {search}")


def official_splits() -> dict[str, str]:
    """Map every source video id to train/val/test using the official FF++ split files."""
    mapping: dict[str, str] = {}
    for split in ("train", "val", "test"):
        for pair in json.loads((SPLITS_DIR / f"{split}.json").read_text()):
            for video_id in pair:
                if mapping.setdefault(video_id, split) != split:
                    raise ValueError(f"video {video_id} appears in two splits")
    return mapping


def split_of(stem: str, mapping: dict[str, str]) -> str | None:
    """Split of a real ("071") or fake ("071_054") video; None if its ids disagree."""
    splits = {mapping.get(part) for part in stem.split("_")}
    return splits.pop() if len(splits) == 1 else None


def discover(root: Path, limit: int | None = None, smoke: bool = False) -> list[Video]:
    mapping = official_splits()
    videos: list[Video] = []
    methods = sorted(
        d.name for d in root.iterdir() if d.is_dir() and d.name not in EXCLUDED_METHODS
    )
    for method in methods:
        per_split: dict[str, int] = {}
        for i, path in enumerate(sorted((root / method).glob("*.mp4"))):
            split = ("train", "val", "test")[i % 3] if smoke else split_of(path.stem, mapping)
            if split is None:
                continue
            if limit is not None and per_split.get(split, 0) >= limit:
                continue
            per_split[split] = per_split.get(split, 0) + 1
            label = 0 if method == REAL else 1
            videos.append(Video(str(path), method, path.stem, label, split))
    return videos


_detector: FaceDetector | None = None


def _init_worker() -> None:
    global _detector  # noqa: PLW0603
    cv2.setNumThreads(1)
    _detector = FaceDetector()


def _extract(job: tuple[Video, str, int, int]) -> list[FaceRow]:
    video, out_dir, frames, size = job
    assert _detector is not None
    target = Path(out_dir) / video.split / video.method
    target.mkdir(parents=True, exist_ok=True)
    rows: list[FaceRow] = []
    try:
        for frame in sample_frames(Path(video.path), frames):
            faces = _detector.detect(frame.image)
            if not faces:
                continue
            crop = crop_face(frame.image, faces[0], size=size)
            name = f"{video.split}/{video.method}/{video.stem}_{frame.index:05d}.jpg"
            cv2.imwrite(str(Path(out_dir) / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            rows.append(FaceRow(name, video.label, video.method, video.key, video.split))
    except Exception as error:
        print(f"[extract] {video.path}: {error!r}", flush=True)
    return rows


def extract_faces(
    videos: list[Video],
    out_dir: Path,
    frames_real_train: int,
    frames_fake_train: int,
    frames_eval: int,
    size: int,
    workers: int,
) -> list[FaceRow]:
    """Crop faces from every video in parallel and write ``manifest.csv``."""

    def frames_for(video: Video) -> int:
        if video.split != "train":
            return frames_eval
        return frames_real_train if video.label == 0 else frames_fake_train

    jobs = [(v, str(out_dir), frames_for(v), size) for v in videos]
    rows: list[FaceRow] = []
    started = time.time()
    with mp.Pool(workers, initializer=_init_worker) as pool:
        for done, result in enumerate(pool.imap_unordered(_extract, jobs, chunksize=4), 1):
            rows.extend(result)
            if done % 250 == 0 or done == len(jobs):
                rate = done / (time.time() - started)
                print(
                    f"[extract] {done}/{len(jobs)} videos, {len(rows)} faces, {rate:.1f} videos/s",
                    flush=True,
                )
    rows.sort(key=lambda r: r.file)
    write_manifest(out_dir / "manifest.csv", rows)
    return rows


def write_manifest(path: Path, rows: list[FaceRow]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FaceRow.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)


def read_manifest(path: Path) -> list[FaceRow]:
    with path.open(newline="") as handle:
        return [
            FaceRow(r["file"], int(r["label"]), r["method"], r["video"], r["split"])
            for r in csv.DictReader(handle)
        ]
