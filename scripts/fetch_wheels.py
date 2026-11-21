"""Download every package of a wheel list so that a broken connection costs nothing.

For slow or unstable internet: ``pip`` starts a broken download from zero and sometimes stops
on a half-received package index. This script needs no index. It fetches a fixed list of files
(``requirements/wheels/*.txt``), continues each file from the byte where the connection
dropped, checks every file against its SHA-256 and can simply be started again at any time.

    python scripts/fetch_wheels.py requirements/wheels/macos-arm64-py313.txt
    pip install --no-index --find-links wheels -e .

Only the standard library is used, so it runs before anything is installed.
"""

from __future__ import annotations

import hashlib
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CHUNK = 64 * 1024
ATTEMPTS = 500  # per file; every attempt continues where the previous one stopped
TIMEOUT = 45.0  # seconds of silence before a connection is considered dead


def tls_context() -> ssl.SSLContext:
    """System certificates plus pip's own bundle.

    Python from python.org on macOS has no certificates until "Install Certificates.command"
    is run; pip always carries a bundle, so HTTPS works there too.
    """
    context = ssl.create_default_context()
    try:
        from pip._vendor import certifi  # noqa: PLC0415

        context.load_verify_locations(certifi.where())
    except Exception:
        pass
    return context


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


TLS = tls_context()


def read_list(path: Path) -> list[tuple[str, int, str]]:
    """Lines of ``sha256 size url``; ``#`` starts a comment. Smallest files first."""
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            digest, size, url = line.split()
            entries.append((digest, int(size), url))
    return sorted(entries, key=lambda entry: entry[1])


def fetch(url: str, part: Path, size: int, label: str) -> None:
    """Append to ``part`` until it holds ``size`` bytes, resuming after every failure."""
    for attempt in range(1, ATTEMPTS + 1):
        have = part.stat().st_size if part.exists() else 0
        if have >= size:
            return
        request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=TLS) as response:
                if have and response.status != 206:  # the server ignored the range
                    have = 0
                with part.open("ab" if have else "wb") as handle:
                    shown = time.time()
                    while block := response.read(CHUNK):
                        handle.write(block)
                        have += len(block)
                        if time.time() - shown > 2:
                            shown = time.time()
                            print(f"\r  {label}: {have / 1e6:.1f} / {size / 1e6:.1f} MB ", end="")
                            sys.stdout.flush()
        except (OSError, urllib.error.URLError) as error:  # timeouts and resets are OSError
            pause = min(30, 2 * attempt)
            print(f"\n  connection lost ({error}); continuing in {pause} s (try {attempt})")
            time.sleep(pause)
    raise SystemExit(f"gave up on {url}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    entries = read_list(Path(sys.argv[1]))
    target = Path(sys.argv[2] if len(sys.argv) > 2 else "wheels")
    target.mkdir(parents=True, exist_ok=True)
    total = sum(size for _, size, _ in entries)
    print(f"{len(entries)} files, {total / 1e6:.0f} MB in total -> {target}/")
    for index, (digest, size, url) in enumerate(entries, 1):
        name = url.rsplit("/", 1)[-1]
        final, label = target / name, f"[{index}/{len(entries)}] {name}"
        if not final.exists() and Path(name).is_file() and Path(name).stat().st_size == size:
            shutil.copyfile(name, final)  # already downloaded by hand into this folder
        for _ in range(3):
            if final.exists() and sha256_of(final) == digest:
                break
            final.unlink(missing_ok=True)
            part = target / (name + ".part")
            fetch(url, part, size, label)
            if sha256_of(part) == digest:
                part.replace(final)
                break
            print(f"\n  {label}: checksum mismatch, downloading again")
            part.unlink()
        else:
            raise SystemExit(f"{name}: the checksum never matched")
        print(f"\r  ok {label} ({size / 1e6:.1f} MB)" + " " * 20)
    print(f"\nAll files are here. Now run:\n  pip install --no-index --find-links {target} -e .")


if __name__ == "__main__":
    main()
