"""Decide what an uploaded file really is, from its bytes rather than its name."""

from __future__ import annotations

from pathlib import Path

from dfd.domain import errors
from dfd.domain.entities import MediaType
from dfd.domain.ports import MediaInfo
from dfd.infrastructure.media.ffmpeg import probe
from dfd.infrastructure.media.frames import read_image

MAX_IMAGE_PIXELS = 64_000_000


def sniff(header: bytes) -> tuple[str, str] | None:
    """Return (family, container) for known signatures; family is 'image' or 'av'."""
    signatures: list[tuple[bytes, int, str, str]] = [
        (b"\xff\xd8\xff", 0, "image", "jpeg"),
        (b"\x89PNG\r\n\x1a\n", 0, "image", "png"),
        (b"BM", 0, "image", "bmp"),
        (b"ftyp", 4, "av", "mp4"),
        (b"\x1a\x45\xdf\xa3", 0, "av", "matroska"),
        (b"fLaC", 0, "av", "flac"),
        (b"OggS", 0, "av", "ogg"),
        (b"ID3", 0, "av", "mp3"),
    ]
    for magic, offset, family, container in signatures:
        if header[offset : offset + len(magic)] == magic:
            return family, container
    if header[:4] == b"RIFF":
        kinds = {b"WEBP": ("image", "webp"), b"WAVE": ("av", "wav"), b"AVI ": ("av", "avi")}
        return kinds.get(header[8:12])
    if len(header) > 1 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0:
        return "av", "mp3"
    return None


class FileInspector:
    def inspect(self, path: Path) -> MediaInfo:
        with path.open("rb") as handle:
            kind = sniff(handle.read(32))
        if kind is None:
            raise errors.UnsupportedMedia()
        family, container = kind
        if family == "image":
            image = read_image(path)
            if image is None:
                raise errors.CorruptMedia()
            height, width = image.shape[:2]
            if width * height > MAX_IMAGE_PIXELS:
                raise errors.FileTooLarge()
            return MediaInfo(MediaType.IMAGE, width=width, height=height, container=container)
        info = probe(path)
        if info.has_video:
            return MediaInfo(
                MediaType.VIDEO,
                duration_s=info.duration_s,
                width=info.width,
                height=info.height,
                has_audio=info.has_audio,
                container=container,
            )
        if info.has_audio:
            return MediaInfo(
                MediaType.AUDIO, duration_s=info.duration_s, has_audio=True, container=container
            )
        raise errors.CorruptMedia()
