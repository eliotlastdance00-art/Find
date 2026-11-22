from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from dfd.infrastructure.media.provenance import MAX_FIELD, image_provenance


def _png(path: Path, **metadata: str) -> Path:
    info = PngInfo()
    for key, value in metadata.items():
        info.add_text(key, value)
    Image.new("RGB", (32, 32), "blue").save(path, pnginfo=info)
    return path


def test_generation_settings_are_hints_not_raw_private_data(tmp_path: Path) -> None:
    path = _png(
        tmp_path / "ai.png", parameters="private prompt\nSteps: 20, Sampler: Euler, Seed: 42"
    )
    assert image_provenance(path) == ["ai_workflow"]


def test_prompt_and_normal_editors_are_not_ai_evidence(tmp_path: Path) -> None:
    path = _png(tmp_path / "real.png", prompt="AI art?", Software="Adobe Photoshop 2026")
    assert image_provenance(path) == []
    path = _png(path, parameters="A photo of someone holding a sign saying Stable Diffusion")
    assert image_provenance(path) == []


@pytest.mark.parametrize("attribute", [False, True])
def test_explicit_iptc_source_type_is_reported(tmp_path: Path, attribute: bool) -> None:
    uri = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
    source = f"<i:DigitalSourceType>{uri}</i:DigitalSourceType>"
    body = f'<rdf:Description i:DigitalSourceType="{uri}" />' if attribute else source
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:i="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">'
        f"{body}</x:xmpmeta>"
    )
    assert image_provenance(_png(tmp_path / "ai.png", **{"XML:com.adobe.xmp": xmp})) == [
        "ai_declared"
    ]


def test_exif_tool_marker_and_png_tool_marker(tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[305] = "ComfyUI"
    path = tmp_path / "ai.jpg"
    Image.new("RGB", (32, 32)).save(path, exif=exif)
    assert image_provenance(path) == ["ai_software"]
    assert image_provenance(_png(tmp_path / "ai.png", Software="Stable Diffusion")) == [
        "ai_software"
    ]


@pytest.mark.parametrize("xmp", ["broken <xml", '<!DOCTYPE x [<!ENTITY x "ai">]><x/>', "C2PA"])
def test_malformed_or_unsigned_payload_is_not_treated_as_proof(tmp_path: Path, xmp: str) -> None:
    assert image_provenance(_png(tmp_path / "metadata.png", xmp=xmp)) == []


def test_large_metadata_field_is_ignored(tmp_path: Path) -> None:
    path = _png(tmp_path / "large.png", Software="ComfyUI" + " " * MAX_FIELD)
    assert image_provenance(path) == []
    assert image_provenance(tmp_path / "missing.png") == []
