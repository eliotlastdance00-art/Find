"""The analysis pipeline: turns a media file into raw findings (``Analysis``)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2

from dfd.domain import errors
from dfd.domain.entities import (
    Analysis,
    FrameFinding,
    MediaType,
    ModalityResult,
    ScanStatus,
    SegmentFinding,
)
from dfd.domain.ports import ProgressCallback
from dfd.domain.scoring import aggregate_scores
from dfd.infrastructure.media import audio as pcm
from dfd.infrastructure.media.faces import Face, FaceDetector, Image, crop_face
from dfd.infrastructure.media.ffmpeg import extract_audio, probe
from dfd.infrastructure.media.frames import read_image, sample_frames
from dfd.infrastructure.ml.audio import SAMPLE_RATE, WINDOW
from dfd.infrastructure.ml.gradcam import overlay_heatmap
from dfd.infrastructure.ml.registry import ModelRegistry

log = logging.getLogger(__name__)

DISPLAY_SIZE = 320
OVERVIEW_SIDE = 960
_JPEG = [cv2.IMWRITE_JPEG_QUALITY, 90]
_BOX_COLOURS = {"real": (94, 197, 34), "suspicious": (11, 158, 245), "fake": (68, 68, 239)}


@dataclass(slots=True)
class _Candidate:
    index: int
    timestamp_s: float | None
    face: Face
    crop: Image
    thumbnail: Image
    scale: float


def _thumbnail(image: Image) -> tuple[Image, float]:
    scale = min(1.0, OVERVIEW_SIDE / max(image.shape[:2]))
    if scale >= 1.0:
        return image.copy(), 1.0
    size = (round(image.shape[1] * scale), round(image.shape[0] * scale))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA), scale


def _write(path: Path, image: Image) -> str:
    cv2.imwrite(str(path), image, _JPEG)
    return path.name


class TorchMediaAnalyzer:
    def __init__(
        self,
        registry: ModelRegistry,
        faces: FaceDetector,
        video_frames: int = 24,
        explain_top_k: int = 6,
        max_faces: int = 4,
        max_audio_s: float = 600.0,
        analyze_video_audio: bool = True,
    ) -> None:
        self._registry = registry
        self._faces = faces
        self._video_frames = video_frames
        self._top_k = explain_top_k
        self._max_faces = max_faces
        self._max_audio_s = max_audio_s
        self._video_audio = analyze_video_audio

    def analyze(
        self, path: Path, media_type: MediaType, workdir: Path, progress: ProgressCallback
    ) -> Analysis:
        workdir.mkdir(parents=True, exist_ok=True)
        if media_type is MediaType.IMAGE:
            return self._image(path, workdir, progress)
        if media_type is MediaType.VIDEO:
            return self._video(path, workdir, progress)
        analysis = Analysis()
        self._audio(path, workdir, analysis, progress, 0.05, 0.95, required=True)
        return analysis

    # -- picture ------------------------------------------------------------------------

    def _image(self, path: Path, workdir: Path, progress: ProgressCallback) -> Analysis:
        detector = self._registry.visual()
        image = read_image(path)
        if image is None:
            raise errors.CorruptMedia()
        found = self._faces.detect(image)
        analysis = Analysis(media_info={"faces_found": len(found)})
        if not found:
            analysis.notes.append("no_face_found")
            return analysis
        if len(found) > self._max_faces:
            analysis.notes.append("faces_truncated")
        thumbnail, scale = _thumbnail(image)
        candidates = [
            _Candidate(i, None, face, crop_face(image, face), thumbnail, scale)
            for i, face in enumerate(found[: self._max_faces])
        ]
        progress(ScanStatus.ANALYZING, 0.35)
        probabilities = detector.predict([c.crop for c in candidates])
        card = detector.card
        thresholds = card.thresholds_for("image")
        analysis.visual = ModalityResult(
            max(probabilities), thresholds, card.label, card.provisional
        )
        progress(ScanStatus.EXPLAINING, 0.6)
        explained = self._explain(
            candidates, probabilities, range(len(candidates)), workdir, progress, 0.6, 0.9
        )
        analysis.frames = [
            FrameFinding(c.index, None, p, c.face.box, *explained.get(c.index, (None, None)))
            for c, p in zip(candidates, probabilities, strict=True)
        ]
        overview = thumbnail.copy()
        for candidate, probability in zip(candidates, probabilities, strict=True):
            self._draw_box(
                overview, candidate, probability, thresholds.real_max, thresholds.fake_min
            )
        analysis.overview_file = _write(workdir / "overview.jpg", overview)
        return analysis

    def _video(self, path: Path, workdir: Path, progress: ProgressCallback) -> Analysis:
        detector = self._registry.visual()
        info = probe(path)
        candidates: list[_Candidate] = []
        sampled = 0
        for frame in sample_frames(path, self._video_frames):
            sampled += 1
            found = self._faces.detect(frame.image)
            if found:
                thumbnail, scale = _thumbnail(frame.image)
                candidates.append(
                    _Candidate(
                        frame.index,
                        frame.timestamp_s,
                        found[0],
                        crop_face(
                            frame.image, found[0], size=max(DISPLAY_SIZE, detector.card.input_size)
                        ),
                        thumbnail,
                        scale,
                    )
                )
            progress(ScanStatus.PREPROCESSING, 0.05 + 0.25 * min(1.0, sampled / self._video_frames))
        if sampled == 0:
            raise errors.CorruptMedia()
        analysis = Analysis(media_info={"frames_sampled": sampled, "faces_found": len(candidates)})
        visual_end = 0.8 if (info.has_audio and self._video_audio) else 0.95
        if not candidates:
            analysis.notes.append("no_face_found")
        else:
            probabilities: list[float] = []
            for start in range(0, len(candidates), 4):
                probabilities += detector.predict([c.crop for c in candidates[start : start + 4]])
                done = len(probabilities) / len(candidates)
                progress(ScanStatus.ANALYZING, 0.3 + (visual_end - 0.5) * done)
            card = detector.card
            thresholds = card.thresholds_for("video")
            analysis.visual = ModalityResult(
                aggregate_scores(probabilities), thresholds, card.label, card.provisional
            )
            ranked = sorted(range(len(candidates)), key=lambda i: probabilities[i], reverse=True)
            explained = self._explain(
                candidates,
                probabilities,
                ranked[: self._top_k],
                workdir,
                progress,
                visual_end - 0.2,
                visual_end,
            )
            analysis.frames = [
                FrameFinding(
                    c.index, c.timestamp_s, p, c.face.box, *explained.get(c.index, (None, None))
                )
                for c, p in zip(candidates, probabilities, strict=True)
            ]
            top = candidates[ranked[0]]
            overview = top.thumbnail.copy()
            self._draw_box(
                overview, top, probabilities[ranked[0]], thresholds.real_max, thresholds.fake_min
            )
            analysis.overview_file = _write(workdir / "overview.jpg", overview)
        if info.has_audio and self._video_audio:
            self._audio(path, workdir, analysis, progress, visual_end, 0.95, required=False)
        return analysis

    def _explain(
        self,
        candidates: list[_Candidate],
        probabilities: list[float],
        chosen: range | list[int],
        workdir: Path,
        progress: ProgressCallback,
        start: float,
        end: float,
    ) -> dict[int, tuple[str, str]]:
        """Write the face crop and its Grad-CAM overlay for the chosen candidates."""
        detector = self._registry.visual()
        files: dict[int, tuple[str, str]] = {}
        picked = list(chosen)
        for done, position in enumerate(picked, 1):
            candidate = candidates[position]
            _, heatmap = detector.explain(candidate.crop)
            face = cv2.resize(
                candidate.crop, (DISPLAY_SIZE, DISPLAY_SIZE), interpolation=cv2.INTER_AREA
            )
            tag = f"{candidate.index:06d}"
            files[candidate.index] = (
                _write(workdir / f"face_{tag}.jpg", face),
                _write(workdir / f"heat_{tag}.jpg", overlay_heatmap(face, heatmap)),
            )
            progress(ScanStatus.EXPLAINING, start + (end - start) * done / len(picked))
        log.debug("explained %d faces, top p=%.3f", len(files), max(probabilities, default=0.0))
        return files

    @staticmethod
    def _draw_box(
        canvas: Image, candidate: _Candidate, probability: float, real_max: float, fake_min: float
    ) -> None:
        verdict = (
            "fake"
            if probability >= fake_min
            else "real"
            if probability <= real_max
            else "suspicious"
        )
        x, y, w, h = (round(v * candidate.scale) for v in candidate.face.box)
        thickness = max(2, round(max(canvas.shape[:2]) / 320))
        cv2.rectangle(canvas, (x, y), (x + w, y + h), _BOX_COLOURS[verdict], thickness)
        label = f"{probability * 100:.0f}%"
        scale = max(0.5, thickness / 4)
        (tw, th), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, scale, max(1, thickness // 2)
        )
        top = max(0, y - th - 8)
        cv2.rectangle(canvas, (x, top), (x + tw + 8, top + th + 8), _BOX_COLOURS[verdict], -1)
        cv2.putText(
            canvas,
            label,
            (x + 4, top + th + 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (255, 255, 255),
            max(1, thickness // 2),
            cv2.LINE_AA,
        )

    # -- sound --------------------------------------------------------------------------

    def _audio(
        self,
        path: Path,
        workdir: Path,
        analysis: Analysis,
        progress: ProgressCallback,
        start: float,
        end: float,
        required: bool,
    ) -> None:
        """Score the sound track. For a video (``required=False``) problems become notes."""
        wav = workdir / "audio.wav"
        try:
            detector = self._registry.audio()
            progress(ScanStatus.PREPROCESSING if required else ScanStatus.ANALYZING, start)
            extract_audio(path, wav, SAMPLE_RATE, self._max_audio_s)
            samples, rate = pcm.read_wav(wav)
            if pcm.is_silent(samples):
                analysis.notes.append("audio_silent")
                return
            batch, spans = pcm.windows(samples, rate, WINDOW, WINDOW // 2)
            probabilities: list[float] = []
            for offset in range(0, len(batch), 4):
                probabilities += detector.predict(batch[offset : offset + 4])
                fraction = len(probabilities) / len(batch)
                progress(ScanStatus.ANALYZING, start + (end - start) * fraction)
            card = detector.card
            analysis.audio = ModalityResult(
                aggregate_scores(probabilities),
                card.thresholds_for("audio"),
                card.label,
                card.provisional,
            )
            analysis.segments = [
                SegmentFinding(span[0], span[1], p)
                for span, p in zip(spans, probabilities, strict=True)
            ]
            analysis.media_info["audio_windows"] = len(batch)
        except errors.ModelUnavailable:
            if required:
                raise
            analysis.notes.append("audio_model_unavailable")
        except errors.CorruptMedia:
            if required:
                raise
            analysis.notes.append("audio_unreadable")
        finally:
            wav.unlink(missing_ok=True)
