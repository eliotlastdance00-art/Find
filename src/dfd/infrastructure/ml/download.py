"""Pinned model distribution: resumable HTTPS, SHA-256 and atomic installation.

Only an explicit CLI command uses the network; the web server never downloads
weights. Partial files survive interruptions, including Ctrl+C. Mirrors must serve
exactly the same pinned bytes. No pickle or remote Python code is involved.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from http.client import HTTPException, HTTPResponse
from pathlib import Path

from dfd.infrastructure.ml.cards import ModelCard, file_sha256, save_card

ASSETS = Path(__file__).parent / "assets"
CHUNK = 1 << 18
_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")


class ModelDownloadError(RuntimeError):
    """No mirror completed a valid, pinned model download."""


def smaug_card() -> ModelCard:
    return ModelCard.from_json(json.loads((ASSETS / "smaug.json").read_text(encoding="utf-8")))


def _tls() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        # python.org macOS may not have run Install Certificates.command yet.
        from pip._vendor import certifi  # noqa: PLC0415

        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return context


def _response_offset(response: HTTPResponse, have: int, size: int) -> int:
    if response.status == 206:
        match = _RANGE.fullmatch(response.headers.get("Content-Range", ""))
        if not match:
            raise ModelDownloadError("missing or invalid Content-Range")
        start, end, total = (int(value) for value in match.groups())
        if start != have or total != size or not start <= end < size:
            raise ModelDownloadError("mirror returned a different byte range")
    elif response.status == 200:
        have = 0  # range ignored: replace the partial file instead of appending
    else:
        raise ModelDownloadError(f"unexpected download status {response.status}")
    length = response.headers.get("Content-Length")
    if length and int(length) > size - have:
        raise ModelDownloadError("mirror returned too many bytes")
    return have


def _transfer(
    url: str,
    part: Path,
    size: int,
    progress: Callable[[str], None],
    timeout: float,
) -> None:
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink()
        have = 0
    if have == size:
        return
    headers = {"User-Agent": "dfd-model-downloader/1", "Accept-Encoding": "identity"}
    if have:
        headers["Range"] = f"bytes={have}-"
    if not url.startswith("https://"):
        raise ModelDownloadError("model downloads require HTTPS")
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout, context=_tls()) as response:
        have = _response_offset(response, have, size)
        announced = have // (10 * CHUNK)
        with part.open("ab" if have else "wb") as handle:
            while block := response.read(CHUNK):
                have += len(block)
                if have > size:
                    raise ModelDownloadError("download exceeds pinned size")
                handle.write(block)
                if have // (10 * CHUNK) > announced:
                    announced = have // (10 * CHUNK)
                    progress(f"Smaug: {have / 1e6:.1f} / {size / 1e6:.1f} MB")
        if have != size:
            raise ModelDownloadError(f"incomplete download ({have}/{size}); partial file kept")


def download_smaug(
    weights_dir: Path,
    progress: Callable[[str], None] = print,
    *,
    attempts: int = 3,
    timeout: float = 45.0,
) -> Path:
    """Install Smaug or verify an existing copy. Re-run safely after a connection loss."""
    card = smaug_card()
    folder = weights_dir / "synthetic"
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / card.weights_file
    part = final.with_suffix(final.suffix + ".part")
    size = int(card.extra["download"]["size"])
    urls = list(card.extra["download"]["urls"])

    if final.is_file() and final.stat().st_size == size and file_sha256(final) == card.sha256:
        save_card(folder, card)
        licence = ASSETS / "LICENSE-Smaug.txt"
        (folder / licence.name).write_bytes(licence.read_bytes())
        progress("Smaug: installed copy verified; nothing to download")
        return final
    last: Exception | None = None
    for _attempt in range(attempts):
        for url in urls:
            try:
                _transfer(url, part, size, progress, timeout)
                if file_sha256(part) != card.sha256:
                    part.unlink(missing_ok=True)
                    raise ModelDownloadError("Smaug SHA-256 mismatch; invalid partial file removed")
                part.replace(final)  # atomic: an incomplete download never becomes a model
                save_card(folder, card)
                licence = ASSETS / "LICENSE-Smaug.txt"
                (folder / licence.name).write_bytes(licence.read_bytes())
                progress("Smaug: SHA-256 verified; installed")
                return final
            except (
                OSError,
                HTTPException,
                urllib.error.URLError,
                ModelDownloadError,
                ValueError,
            ) as error:
                last = error
                progress(f"Smaug download interrupted: {error}; retrying/moving to mirror")
    raise ModelDownloadError(
        f"Smaug was not installed: {last}. Partial file kept at {part}. "
        "Run 'dfd models --download' again to continue."
    )
