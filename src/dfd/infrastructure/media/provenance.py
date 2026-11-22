"""Unverified, privacy-preserving AI declarations from structured image metadata.

These are hints, NOT C2PA signature verification and NOT grounds for a verdict.
Do not search the compressed image bytes, expose prompts/GPS, or infer authenticity
from the absence of metadata. A normal editor's Software tag is not an AI marker.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

log = logging.getLogger(__name__)
MAX_FIELD = 256 * 1024
DIGITAL_SOURCE = "{http://iptc.org/std/Iptc4xmpExt/2008-02-29/}DigitalSourceType"
AI_SOURCES = {
    "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
    "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
}
AI_TOOLS = re.compile(
    r"\b(?:stable diffusion|comfyui|automatic1111|invokeai|midjourney|dall-e)\b", re.I
)


def _string(value: object) -> str:
    if isinstance(value, bytes) and len(value) <= MAX_FIELD:
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) and len(value) <= MAX_FIELD else ""


def _xmp_declares_ai(value: object) -> bool:
    source = _string(value)
    if not source or "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        return False
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        return False
    for node in root.iter():
        if node.attrib.get(DIGITAL_SOURCE, "").strip() in AI_SOURCES:
            return True
        if node.tag == DIGITAL_SOURCE and any(
            (child.text or "").strip() in AI_SOURCES for child in node.iter()
        ):
            return True
    return False


def image_provenance(path: Path) -> list[str]:
    """Return stable translation codes, never the user's raw metadata contents."""
    findings: set[str] = set()
    try:
        with Image.open(path) as image:
            info = image.info
            if any(_xmp_declares_ai(info.get(key)) for key in ("xmp", "XML:com.adobe.xmp")):
                findings.add("ai_declared")
            # A prompt/description alone is NOT evidence. Require SD's structured fields.
            parameters = _string(info.get("parameters"))
            if all(
                re.search(rf"\b{key}:\s*\S", parameters) for key in ("Steps", "Sampler", "Seed")
            ):
                findings.add("ai_workflow")
            software = _string(image.getexif().get(305)) or _string(info.get("Software"))
            if AI_TOOLS.search(software):
                findings.add("ai_software")
    except (OSError, ValueError, SyntaxError, TypeError) as error:
        # Optional metadata must never prevent decoded pixels from being analysed.
        log.debug("could not read image metadata: %s", error)
    return sorted(findings)
