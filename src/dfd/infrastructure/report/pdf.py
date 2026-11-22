"""PDF report rendering with fpdf2 and DejaVu Sans (covers Turkmen and Cyrillic)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from dfd.domain.entities import Scan, Verdict
from dfd.infrastructure.report.texts import DEFAULT_LANGUAGE, LANGUAGES, text

FONTS = Path(__file__).parent / "fonts"
INK = (17, 24, 39)
MUTED = (107, 114, 128)
LINE = (229, 231, 235)
BRAND = (79, 70, 229)
VERDICT_COLOURS = {
    Verdict.REAL: (22, 163, 74),
    Verdict.SUSPICIOUS: (217, 119, 6),
    Verdict.FAKE: (220, 38, 38),
    Verdict.INCONCLUSIVE: (107, 114, 128),
}
MAX_GALLERY = 6


def _size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _colour_for(prob: float, real_max: float, fake_min: float) -> tuple[int, int, int]:
    if prob >= fake_min:
        return VERDICT_COLOURS[Verdict.FAKE]
    if prob <= real_max:
        return VERDICT_COLOURS[Verdict.REAL]
    return VERDICT_COLOURS[Verdict.SUSPICIOUS]


class _Report(FPDF):  # type: ignore[misc]
    def __init__(self, lang: str) -> None:
        super().__init__(format="A4", unit="mm")
        self.lang = lang
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=18)
        self.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        self.alias_nb_pages()

    def t(self, key: str) -> str:
        return text(key, self.lang)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*MUTED)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        self.cell(0, 5, f"{self.t('generated')}: {stamp}", align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"{self.t('page')} {self.page_no()} / {{nb}}", align="R")

    def heading(self, label: str) -> None:
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(3)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*INK)
        self.cell(0, 7, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2.5)

    def row(self, label: str, value: str) -> None:
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(*MUTED)
        self.cell(42, 5.5, label)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def paragraph(self, body: str, size: float = 8.5, muted: bool = False) -> None:
        self.set_font("DejaVu", "", size)
        self.set_text_color(*(MUTED if muted else INK))
        self.multi_cell(0, 4.6, body, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bars(
        self, values: list[float], real_max: float, fake_min: float, height: float = 26
    ) -> None:
        """Bar chart of probabilities with the decision band drawn as dashed lines."""
        if self.get_y() + height + 10 > self.h - self.b_margin:
            self.add_page()
        left, top = self.l_margin + 8, self.get_y()
        width = self.w - self.r_margin - left
        self.set_draw_color(*LINE)
        self.rect(left, top, width, height)
        self.set_font("DejaVu", "", 6.5)
        self.set_text_color(*MUTED)
        for level in (0.0, 0.5, 1.0):
            y = top + height * (1 - level)
            self.text(self.l_margin, y + 1, f"{level * 100:.0f}%")
        shown = values[:120]
        slot = width / max(1, len(shown))
        for i, value in enumerate(shown):
            bar = max(0.3, height * min(1.0, max(0.0, value)))
            self.set_fill_color(*_colour_for(value, real_max, fake_min))
            self.rect(
                left + i * slot + slot * 0.12, top + height - bar, slot * 0.76, bar, style="F"
            )
        self.set_draw_color(*MUTED)
        self.set_dash_pattern(dash=1, gap=1)
        for level in (real_max, fake_min):
            y = top + height * (1 - level)
            self.line(left, y, left + width, y)
        self.set_dash_pattern()
        self.set_y(top + height + 3)


class PdfReportRenderer:
    def render(self, scan: Scan, username: str, lang: str, artifacts: Path) -> bytes:
        lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
        pdf = _Report(lang)
        pdf.set_title(f"{pdf.t('title')} - {scan.filename}")
        pdf.set_author(pdf.t("subtitle"))
        pdf.add_page()
        self._header(pdf)
        self._file(pdf, scan, username)
        self._verdict(pdf, scan)
        details = scan.details
        self._modalities(pdf, scan, details)
        if scan.media_type.value == "image":
            self._provenance(pdf, details)
        self._timelines(pdf, details)
        self._gallery(pdf, details, artifacts)
        self._notes(pdf, scan, details)
        pdf.heading(pdf.t("disclaimer_title"))
        pdf.paragraph(pdf.t("disclaimer"), size=8, muted=True)
        return bytes(pdf.output())

    @staticmethod
    def _header(pdf: _Report) -> None:
        pdf.set_fill_color(*BRAND)
        pdf.rect(0, 0, pdf.w, 26, style="F")
        pdf.set_xy(pdf.l_margin, 7)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 15)
        pdf.cell(0, 7, pdf.t("title"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("DejaVu", "", 8.5)
        pdf.cell(0, 5, pdf.t("subtitle"))
        pdf.set_y(31)

    @staticmethod
    def _file(pdf: _Report, scan: Scan, username: str) -> None:
        media = scan.details.get("media", {})
        pdf.heading(pdf.t("file"))
        pdf.row(pdf.t("name"), scan.filename)
        pdf.row(pdf.t("type"), pdf.t(scan.media_type.value))
        pdf.row(pdf.t("size"), _size(scan.size_bytes))
        if media.get("duration_s"):
            pdf.row(pdf.t("duration"), f"{media['duration_s']:.1f} {pdf.t('seconds')}")
        if media.get("width") and media.get("height"):
            pdf.row(pdf.t("resolution"), f"{media['width']} x {media['height']}")
        pdf.row("SHA-256", scan.sha256)
        pdf.row(pdf.t("uploaded"), scan.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"))
        pdf.row(pdf.t("user"), username)
        pdf.row(pdf.t("scan_id"), scan.id)

    @staticmethod
    def _verdict(pdf: _Report, scan: Scan) -> None:
        verdict = scan.verdict or Verdict.INCONCLUSIVE
        colour = VERDICT_COLOURS[verdict]
        pdf.heading(pdf.t("result"))
        top = pdf.get_y()
        width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_fill_color(*colour)
        pdf.rect(pdf.l_margin, top, width, 22, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(pdf.l_margin + 6, top + 3.5)
        pdf.set_font("DejaVu", "", 8)
        pdf.cell(100, 4.5, pdf.t("verdict"), new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.set_font("DejaVu", "B", 17)
        pdf.cell(100, 9, pdf.t(verdict.value))
        if scan.prob_fake is not None:
            pdf.set_xy(pdf.l_margin, top + 3.5)
            pdf.set_font("DejaVu", "", 8)
            pdf.cell(
                width - 6,
                4.5,
                pdf.t("score" if scan.details.get("synthetic") else "probability"),
                align="R",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.set_font("DejaVu", "B", 17)
            digits = 2 if scan.details.get("synthetic") else 1
            pdf.cell(width - 6, 9, f"{scan.prob_fake * 100:.{digits}f}%", align="R")
        pdf.set_y(top + 25)

    @staticmethod
    def _modalities(pdf: _Report, scan: Scan, details: dict[str, Any]) -> None:
        rows: list[tuple[str, dict[str, Any]]] = [
            (key, details[key]) for key in ("visual", "synthetic", "audio") if details.get(key)
        ]
        if not rows:
            return
        pdf.heading(pdf.t("modalities"))
        widths = (38, 28, 34, 34, 44)
        headers = ("modality", "probability", "verdict", "band", "model")
        pdf.set_font("DejaVu", "B", 7.5)
        pdf.set_text_color(*MUTED)
        for width, key in zip(widths, headers, strict=True):
            label = "%" if key == "probability" else pdf.t(key)
            pdf.cell(width, 6, label)
        pdf.ln(6)
        pdf.set_font("DejaVu", "", 8.5)
        for key, value in rows:
            pdf.set_text_color(*INK)
            pdf.cell(widths[0], 6, pdf.t("sound" if key == "audio" else key))
            digits = 2 if key == "synthetic" else 1
            pdf.cell(widths[1], 6, f"{value['prob'] * 100:.{digits}f}%")
            pdf.set_text_color(*VERDICT_COLOURS[Verdict(value["verdict"])])
            pdf.cell(widths[2], 6, pdf.t(value["verdict"]))
            pdf.set_text_color(*INK)
            band = f"{value['fake_min'] * 100:.0f}%"
            if value["real_max"] != value["fake_min"]:
                band = f"{value['real_max'] * 100:.0f}% - {band}"
            pdf.cell(widths[3], 6, band)
            pdf.cell(widths[4], 6, str(value["model"])[:30])
            pdf.ln(6)
        del scan

    @staticmethod
    def _provenance(pdf: _Report, details: dict[str, Any]) -> None:
        if "provenance" not in details:
            return
        pdf.heading(pdf.t("provenance"))
        findings = details.get("provenance") or []
        if not findings:
            pdf.paragraph(pdf.t("provenance_none"), muted=True)
        for code in findings:
            pdf.paragraph(pdf.t(f"provenance_{code}"))

    @staticmethod
    def _timelines(pdf: _Report, details: dict[str, Any]) -> None:
        frames, visual = details.get("frames") or [], details.get("visual")
        if len(frames) > 1 and visual:
            pdf.heading(pdf.t("timeline_frames"))
            pdf.bars([f["prob"] for f in frames], visual["real_max"], visual["fake_min"])
        segments, audio = details.get("segments") or [], details.get("audio")
        if len(segments) > 1 and audio:
            pdf.heading(pdf.t("timeline_audio"))
            pdf.bars([s["prob"] for s in segments], audio["real_max"], audio["fake_min"])

    @staticmethod
    def _gallery(pdf: _Report, details: dict[str, Any], artifacts: Path) -> None:
        frames = [f for f in details.get("frames") or [] if f.get("face") and f.get("heatmap")]
        frames = [
            f
            for f in frames
            if (artifacts / f["face"]).is_file() and (artifacts / f["heatmap"]).is_file()
        ]
        if not frames:
            return
        frames.sort(key=lambda f: f["prob"], reverse=True)
        tile, gap, per_row = 27.0, 2.0, 3
        if pdf.get_y() + tile + 34 > pdf.h - pdf.b_margin:
            pdf.add_page()  # keep the heading together with the first row of pictures
        pdf.heading(pdf.t("regions"))
        pdf.paragraph(pdf.t("regions_hint"), size=8, muted=True)
        pdf.ln(1.5)
        pair = tile * 2 + gap
        stride = (pdf.w - pdf.l_margin - pdf.r_margin - pair * per_row) / (per_row - 1) + pair
        for i, frame in enumerate(frames[:MAX_GALLERY]):
            column = i % per_row
            if column == 0 and pdf.get_y() + tile + 12 > pdf.h - pdf.b_margin:
                pdf.add_page()
            if column == 0:
                row_top = pdf.get_y()
            x = pdf.l_margin + column * stride
            pdf.image(str(artifacts / frame["face"]), x=x, y=row_top, w=tile, h=tile)
            pdf.image(
                str(artifacts / frame["heatmap"]), x=x + tile + gap, y=row_top, w=tile, h=tile
            )
            pdf.set_xy(x, row_top + tile + 0.8)
            pdf.set_font("DejaVu", "", 7.5)
            pdf.set_text_color(*INK)
            if frame.get("t") is not None:
                label = f"{pdf.t('frame')} {frame['index']} · {frame['t']:.1f} {pdf.t('seconds')}"
            else:
                label = f"{pdf.t('face')} {frame['index'] + 1}"
            pdf.cell(pair, 4.5, f"{label} · {frame['prob'] * 100:.1f}%")
            if column == per_row - 1 or i == min(len(frames), MAX_GALLERY) - 1:
                pdf.set_y(row_top + tile + 8)

    @staticmethod
    def _notes(pdf: _Report, scan: Scan, details: dict[str, Any]) -> None:
        notes = [pdf.t(f"note_{code}") for code in details.get("notes") or []]
        if any((details.get(k) or {}).get("provisional") for k in ("visual", "synthetic", "audio")):
            notes.append(pdf.t("note_provisional"))
        if scan.media_type.value == "video" and details.get("audio"):
            notes.append(pdf.t("note_video_audio"))
        if not notes:
            return
        pdf.heading(pdf.t("notes"))
        for note in notes:
            pdf.paragraph(f"•  {note}")
