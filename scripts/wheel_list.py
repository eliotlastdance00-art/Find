"""Write the wheel list of one platform for ``scripts/fetch_wheels.py``.

The versions come from ``constraints.txt`` (the tested set); the build tools needed for
``pip install -e .`` are added. Only macOS on Apple Silicon is generated for now: there every
package, PyTorch included, is on PyPI.

    python scripts/wheel_list.py 3.13 > requirements/wheels/macos-arm64-py313.txt
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC_ARM64 = [f"macosx_{v}_0_arm64" for v in (11, 12, 13, 14)] + [
    f"macosx_{v}_universal2" for v in ("10_9", "10_12", "10_13", "11_0")
]
BUILD_TOOLS = ["hatchling", "editables"]


def report(arguments: list[str]) -> list[tuple[str, str]]:
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "report.json"
        command = [sys.executable, "-m", "pip", "install", "--quiet", "--dry-run"]
        command += ["--ignore-installed", "--report", str(out), *arguments]
        subprocess.run(command, check=True)
        items = json.loads(out.read_text())["install"]
    return [
        (item["download_info"]["archive_info"]["hashes"]["sha256"], item["download_info"]["url"])
        for item in items
    ]


def main() -> None:
    python = sys.argv[1]
    tag = "cp" + python.replace(".", "")
    pinned = [
        line
        for line in (ROOT / "constraints.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    platform = [flag for name in MAC_ARM64 for flag in ("--platform", name)]
    with tempfile.TemporaryDirectory() as scratch:
        wanted = ["--no-deps", "--only-binary=:all:", "--python-version", python]
        wanted += ["--implementation", "cp", "--abi", tag, "--abi", "abi3", "--abi", "none"]
        files = report([*wanted, *platform, "--target", scratch, *pinned])
    files += report(BUILD_TOOLS)  # pure Python, the same on every platform
    print(f"# macOS arm64, Python {python}: sha256 size url (made by scripts/wheel_list.py)")
    for digest, url in sorted(set(files), key=lambda entry: entry[1].rsplit("/", 1)[-1]):
        head = urllib.request.Request(url, method="HEAD")
        size = urllib.request.urlopen(head, timeout=60).headers["Content-Length"]
        print(digest, size, url)


if __name__ == "__main__":
    main()
