from __future__ import annotations

import hashlib
import io
import ssl
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from dfd.infrastructure.ml import download as dl
from dfd.infrastructure.ml.cards import load_card

DATA = b"abcdef"


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, **headers: str) -> None:
        super().__init__(body)
        self.status = status
        self.headers = headers


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    card = replace(
        dl.smaug_card(),
        sha256=hashlib.sha256(DATA).hexdigest(),
        extra={"download": {"size": len(DATA), "urls": ["https://one/a", "https://two/a"]}},
    )
    monkeypatch.setattr(dl, "smaug_card", lambda: card)
    monkeypatch.setattr(dl, "_tls", lambda: None)


def _part(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "synthetic" / "model.onnx.part"
    path.parent.mkdir()
    path.write_bytes(data)
    return path


def test_resume_verify_atomic_install_and_reuse(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = _part(tmp_path, DATA[:2])
    open_url = Mock(return_value=Response(DATA[2:], 206, **{"Content-Range": "bytes 2-5/6"}))
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    final = dl.download_smaug(tmp_path, progress=Mock())
    assert final.read_bytes() == DATA and not part.exists()
    assert open_url.call_args.args[0].get_header("Range") == "bytes=2-"
    assert load_card(final.parent).sha256 == hashlib.sha256(DATA).hexdigest()
    assert (final.parent / "LICENSE-Smaug.txt").exists()
    assert dl.download_smaug(tmp_path, progress=Mock()) == final
    assert open_url.call_count == 1  # existing hash-verified file requires no network


def test_ignored_range_restarts_instead_of_concatenating(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _part(tmp_path, DATA[:2])
    monkeypatch.setattr(dl.urllib.request, "urlopen", Mock(return_value=Response(DATA)))
    assert dl.download_smaug(tmp_path, progress=Mock()).read_bytes() == DATA


def test_invalid_range_is_rejected_then_mirror_is_used(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _part(tmp_path, DATA[:2])
    open_url = Mock(
        side_effect=[
            Response(b"def", 206, **{"Content-Range": "bytes 3-5/6"}),
            Response(DATA[2:], 206, **{"Content-Range": "bytes 2-5/6"}),
        ]
    )
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    assert dl.download_smaug(tmp_path, progress=Mock()).read_bytes() == DATA
    assert open_url.call_count == 2


def test_interrupted_connection_keeps_bytes_for_mirror(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = Response(b"abc")
    broken.read = Mock(side_effect=[b"abc", OSError("connection reset")])
    open_url = Mock(side_effect=[broken, Response(b"def", 206, **{"Content-Range": "bytes 3-5/6"})])
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    assert dl.download_smaug(tmp_path, progress=Mock()).read_bytes() == DATA
    assert open_url.call_args_list[1].args[0].get_header("Range") == "bytes=3-"


def test_checksum_failure_cannot_install_a_model(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dl.urllib.request, "urlopen", lambda *a, **k: Response(b"xxxxxx"))
    with pytest.raises(dl.ModelDownloadError, match="SHA-256"):
        dl.download_smaug(tmp_path, progress=Mock(), attempts=1)
    assert not (tmp_path / "synthetic" / "model.onnx").exists()
    assert not (tmp_path / "synthetic" / "model_card.json").exists()


def test_short_download_is_kept_for_next_cli_invocation(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_url = Mock(side_effect=[Response(b"abc"), OSError("offline")])
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    with pytest.raises(dl.ModelDownloadError, match="again to continue"):
        dl.download_smaug(tmp_path, progress=Mock(), attempts=1)
    assert (tmp_path / "synthetic" / "model.onnx.part").read_bytes() == b"abc"
    assert not (tmp_path / "synthetic" / "model.onnx").exists()


@pytest.mark.parametrize("headers", [{}, {"Content-Range": "bytes 0-5/100"}])
def test_missing_or_wrong_size_range_is_rejected(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    monkeypatch.setattr(
        dl.urllib.request, "urlopen", lambda *a, **k: Response(DATA, 206, **headers)
    )
    with pytest.raises(dl.ModelDownloadError):
        dl.download_smaug(tmp_path, progress=Mock(), attempts=1)
    assert not (tmp_path / "synthetic" / "model.onnx").exists()


def test_oversized_partial_is_discarded(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _part(tmp_path, b"x" * 20)
    open_url = Mock(return_value=Response(DATA))
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    assert dl.download_smaug(tmp_path, progress=Mock()).read_bytes() == DATA
    assert open_url.call_args.args[0].get_header("Range") is None


def test_complete_partial_file_is_verified_without_network(
    tmp_path: Path, pinned: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _part(tmp_path, DATA)
    open_url = Mock(side_effect=AssertionError("no network expected"))
    monkeypatch.setattr(dl.urllib.request, "urlopen", open_url)
    assert dl.download_smaug(tmp_path, progress=Mock()).read_bytes() == DATA
    open_url.assert_not_called()


@pytest.mark.parametrize(
    "body,status,headers",
    [(DATA, 500, {}), (DATA, 200, {"Content-Length": "20"}), (b"toolong", 200, {})],
)
def test_unexpected_responses_never_become_weights(
    tmp_path: Path,
    pinned: None,
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    status: int,
    headers: dict[str, str],
) -> None:
    monkeypatch.setattr(
        dl.urllib.request, "urlopen", lambda *a, **k: Response(body, status, **headers)
    )
    with pytest.raises(dl.ModelDownloadError):
        dl.download_smaug(tmp_path, progress=Mock(), attempts=1)
    assert not (tmp_path / "synthetic" / "model.onnx").exists()


def test_tls_is_never_disabled() -> None:
    assert dl._tls().verify_mode == ssl.CERT_REQUIRED


def test_non_https_model_url_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(dl.ModelDownloadError, match="HTTPS"):
        dl._transfer("http://one/a", tmp_path / "part", 6, Mock(), 1)
