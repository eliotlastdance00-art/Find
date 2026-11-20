"""Thin, defensive wrapper around the ffmpeg binary (probing and audio extraction)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dfd.domain.errors import CorruptMedia

_DURATION = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_STREAM = re.compile(r"Stream #\d+:\d+.*?: (Video|Audio): (\w+)(.*)")
_SIZE = re.compile(r"\b(\d{2,5})x(\d{2,5})\b")
_FPS = re.compile(r"([\d.]+) fps")
_RATE = re.compile(r"(\d+) Hz")


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """Resolve ffmpeg: $DFD_FFMPEG, then PATH, then the binary bundled with imageio-ffmpeg."""
    configured = os.environ.get("DFD_FFMPEG")
    if configured:
        return configured
    system = shutil.which("ffmpeg")
    if system:
        return system
    import imageio_ffmpeg  # noqa: PLC0415

    return str(imageio_ffmpeg.get_ffmpeg_exe())


@dataclass(frozen=True, slots=True)
class MediaProbe:
    has_video: bool = False
    has_audio: bool = False
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None


def parse_probe(stderr: str) -> MediaProbe:
    """Parse the stream summary that ``ffmpeg -i`` prints."""
    fields: dict[str, object] = {}
    match = _DURATION.search(stderr)
    if match:
        hours, minutes, seconds = match.groups()
        fields["duration_s"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    for kind, codec, rest in _STREAM.findall(stderr):
        if kind == "Video" and "attached pic" not in rest and not fields.get("has_video"):
            fields.update(has_video=True, video_codec=codec)
            if size := _SIZE.search(rest):
                fields.update(width=int(size.group(1)), height=int(size.group(2)))
            if fps := _FPS.search(rest):
                fields["fps"] = float(fps.group(1))
        elif kind == "Audio" and not fields.get("has_audio"):
            fields.update(has_audio=True, audio_codec=codec)
            if rate := _RATE.search(rest):
                fields["sample_rate"] = int(rate.group(1))
    return MediaProbe(**fields)  # type: ignore[arg-type]


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CorruptMedia("ffmpeg timed out") from error
    except OSError as error:
        raise RuntimeError(f"ffmpeg is not available: {error}") from error


def probe(path: Path, timeout: float = 30.0) -> MediaProbe:
    return parse_probe(_run(["-i", str(path)], timeout).stderr)


def extract_audio(
    source: Path,
    target: Path,
    sample_rate: int = 16000,
    max_seconds: float | None = None,
    timeout: float = 300.0,
) -> Path:
    """Decode the first audio stream to mono 16-bit PCM WAV at ``sample_rate``.

    No filtering or silence trimming on purpose: the anti-spoofing model was trained on
    untouched recordings and is known to be sensitive to such "clean-up".
    """
    args = ["-y", "-i", str(source), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", str(sample_rate)]
    if max_seconds:
        args += ["-t", f"{max_seconds:.3f}"]
    args += ["-c:a", "pcm_s16le", str(target)]
    result = _run(args, timeout)
    if result.returncode != 0 or not target.is_file() or target.stat().st_size <= 44:
        raise CorruptMedia("audio stream could not be decoded")
    return target
