"""Download the real (bona fide) Turkmen speech: TurkmenSpeech and Common Voice.

    python -m training.tk_audio.sources --ts-videos 482 --ts-per-video 10 --cv-per-speaker 120

TurkmenSpeech has no speaker labels, so clips are grouped (and later split) by source video;
Common Voice clips are grouped by speaker. Roughly half of the files listed in TurkmenSpeech's
index do not exist on the Hub, so a missing file is replaced by another clip of the same video.
"""

from __future__ import annotations

import argparse
import csv
import io
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from training.tk_audio.common import Job, Sink, read_audio, split_of, stable_hash, work_root

HUB = "https://huggingface.co/datasets"
TS_REPO = "rozumov/TurkmenSpeech"
CV_REPO = "fsicoli/common_voice_22_0"
TS_SECONDS = (3.0, 12.0)
CV_SECONDS = (2.0, 12.0)


def fetch(url: str, timeout: float = 120.0, retries: int = 3) -> bytes | None:
    """Body of ``url``; None when the file does not exist. Transient errors are retried."""
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404):
                return None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2.0 * (attempt + 1))
    return None


def video_id(source_url: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(source_url).query)
    return query.get("v", [source_url.rsplit("/", 1)[-1]])[0]


def decode(data: bytes, suffix: str) -> tuple[object, int]:
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        return read_audio(tmp.name)


# --- TurkmenSpeech ----------------------------------------------------------------------


def turkmenspeech(videos: int, per_video: int, threads: int) -> None:
    sink = Sink("real_ts", kind="bonafide", model=TS_REPO, label=0)
    raw = fetch(f"{HUB}/{TS_REPO}/resolve/main/data/metadata.csv")
    if raw is None:
        raise RuntimeError("TurkmenSpeech index could not be downloaded")
    by_video: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        if TS_SECONDS[0] <= float(row["duration"]) <= TS_SECONDS[1] and row["text"].strip():
            by_video[video_id(row["source"])].append(row)
    chosen = sorted(by_video, key=lambda v: stable_hash("video:" + v))[:videos]
    print(f"[real_ts] {len(by_video)} videos in the index, using {len(chosen)}", flush=True)

    def one_video(video: str) -> list[tuple[dict[str, str], bytes]]:
        rows = sorted(by_video[video], key=lambda r: stable_hash(r["id"]))
        got: list[tuple[dict[str, str], bytes]] = []
        for row in rows[: per_video * 5]:  # give up on a video after 5x as many attempts
            if len(got) == per_video:
                break
            url = f"{HUB}/{TS_REPO}/resolve/main/data/{urllib.parse.quote(row['audio'])}"
            data = fetch(url, timeout=60.0)
            if data:
                got.append((row, data))
        return got

    with ThreadPoolExecutor(threads) as pool:
        for count, (video, clips) in enumerate(
            zip(chosen, pool.map(one_video, chosen), strict=True), 1
        ):
            for row, data in clips:
                clip_id = f"ts_{stable_hash(row['id']):016x}"
                if clip_id in sink.done:
                    continue
                try:
                    wav, rate = decode(data, ".wav")
                except Exception as error:
                    print(f"[real_ts] unreadable {row['id']}: {error!r}", flush=True)
                    continue
                job: Job = {
                    "id": clip_id,
                    "source": "ts",
                    "group": "ts_" + video,
                    "split": split_of("ts_" + video),
                    "text": row["text"].strip(),
                }
                sink.save(job, wav, rate, origin=row["id"])
            if count % 25 == 0 or count == len(chosen):
                print(f"[real_ts] {count}/{len(chosen)} videos: {sink.summary()}", flush=True)


# --- Common Voice -----------------------------------------------------------------------


def common_voice(parts: list[str], per_speaker: int) -> None:
    sink = Sink("real_cv", kind="bonafide", model=CV_REPO, label=0)
    taken: dict[str, int] = defaultdict(int)
    for part in parts:
        table = fetch(f"{HUB}/{CV_REPO}/resolve/main/transcript/tk/{part}.tsv")
        archive = fetch(f"{HUB}/{CV_REPO}/resolve/main/audio/tk/{part}/tk_{part}_0.tar", 600.0)
        if table is None or archive is None:
            print(f"[real_cv] part {part!r} is missing on the Hub, skipped", flush=True)
            continue
        reader = csv.DictReader(
            io.StringIO(table.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE
        )
        rows = {row["path"]: row for row in reader}
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            members = sorted(
                (m for m in tar.getmembers() if m.isfile() and Path(m.name).name in rows),
                key=lambda m: stable_hash(m.name),  # which clips survive the cap is not by order
            )
            for member in members:
                row = rows[Path(member.name).name]
                speaker = "cv_" + row["client_id"][:16]
                clip_id = "cv_" + Path(member.name).stem.rsplit("_", 1)[-1]
                if taken[speaker] >= per_speaker or not row["sentence"].strip():
                    continue
                if clip_id in sink.done:
                    taken[speaker] += 1
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                try:
                    wav, rate = decode(handle.read(), ".mp3")
                except Exception as error:
                    print(f"[real_cv] unreadable {member.name}: {error!r}", flush=True)
                    continue
                if not CV_SECONDS[0] <= len(wav) / rate <= CV_SECONDS[1]:  # type: ignore[arg-type]
                    continue
                job: Job = {
                    "id": clip_id,
                    "source": "cv",
                    "group": speaker,
                    "split": split_of(speaker),
                    "text": row["sentence"].strip(),
                }
                if sink.save(job, wav, rate, origin=Path(member.name).name, cv_part=part):
                    taken[speaker] += 1
        print(f"[real_cv] after {part}: {sink.summary()}, {len(taken)} speakers", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ts-videos", type=int, default=482)
    parser.add_argument("--ts-per-video", type=int, default=10)
    parser.add_argument("--cv-parts", default="train,dev,test,other")
    parser.add_argument("--cv-per-speaker", type=int, default=120)
    parser.add_argument("--threads", type=int, default=16)
    args = parser.parse_args(argv)
    work_root().mkdir(parents=True, exist_ok=True)
    common_voice([p for p in args.cv_parts.split(",") if p], args.cv_per_speaker)
    turkmenspeech(args.ts_videos, args.ts_per_video, args.threads)


if __name__ == "__main__":
    main()
