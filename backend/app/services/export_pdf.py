"""将 export.md 文本转为 PDF（fpdf2 + 系统中文字体）。"""

from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

# Windows 常见中文字体；可通过 PDF_FONT_PATH 覆盖
_DEFAULT_FONT_CANDIDATES = [
    Path(os.environ.get("PDF_FONT_PATH", "")),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
]


def _resolve_cjk_font() -> Path | None:
    for candidate in _DEFAULT_FONT_CANDIDATES:
        if candidate and candidate.is_file():
            return candidate
    return None


def _strip_inline_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


class _DebatePdf(FPDF):
    def __init__(self, font_path: Path | None) -> None:
        super().__init__()
        self._font_path = font_path
        self._font_name = "Helvetica"
        if font_path:
            try:
                self.add_font("CJK", "", str(font_path))
                self._font_name = "CJK"
            except Exception:
                self._font_name = "Helvetica"
        self.set_margins(16, 18, 16)

    def _set_body_size(self, size: float = 11) -> None:
        self.set_font(self._font_name, size=size)

    def header(self) -> None:
        if self.page_no() <= 1:
            return
        self.set_draw_color(218, 211, 202)
        self.line(16, 12, 194, 12)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_text_color(126, 112, 96)
        self._set_body_size(8)
        self.cell(0, 6, f"AI辩论场复盘报告 · {self.page_no()}", align="C")
        self.set_text_color(36, 32, 28)

    def write_title(self, text: str) -> None:
        self.set_fill_color(38, 35, 31)
        self.rect(0, 0, 210, 38, "F")
        self.set_y(16)
        self.set_text_color(255, 248, 239)
        self._set_body_size(20)
        self.multi_cell(0, 9, _strip_inline_md(text), align="C")
        self.set_y(46)
        self.set_text_color(36, 32, 28)

    def write_heading(self, text: str, size: float, level: int = 2) -> None:
        if self.get_y() > 255:
            self.add_page()
        if level == 2:
            self.ln(2)
            self.set_fill_color(247, 241, 231)
            self.set_draw_color(215, 203, 188)
            self.set_text_color(44, 36, 30)
            self._set_body_size(13)
            self.cell(0, 9, _strip_inline_md(text), border=1, ln=1, fill=True)
            self.ln(2)
            return
        self.set_text_color(52, 46, 39)
        self._set_body_size(size)
        self.multi_cell(0, max(6, size * 0.5), _strip_inline_md(text))
        self.ln(1)

    def write_paragraph(self, text: str) -> None:
        if not text.strip():
            self.ln(2)
            return
        self.set_text_color(44, 39, 34)
        self._set_body_size(11)
        self.multi_cell(0, 6, _strip_inline_md(text))
        self.ln(1)

    def write_quote(self, text: str) -> None:
        self.set_fill_color(250, 247, 242)
        self.set_draw_color(215, 203, 188)
        self.set_text_color(84, 70, 58)
        self._set_body_size(10)
        self.multi_cell(0, 6, _strip_inline_md(text), border="L", fill=True)
        self.ln(2)
        self.set_text_color(44, 39, 34)

    def write_bullet(self, text: str) -> None:
        self.set_x(20)
        self.write_paragraph(f"• {_strip_inline_md(text)}")

    def write_table_row(self, cells: list[str], *, header: bool = False) -> None:
        if len(cells) < 2:
            return
        label = _strip_inline_md(cells[0].strip())
        value = " · ".join(_strip_inline_md(cell.strip()) for cell in cells[1:] if cell.strip())
        if not label and not value:
            return
        if header:
            self.set_fill_color(232, 224, 214)
            self.set_text_color(52, 46, 39)
        else:
            self.set_fill_color(253, 251, 247)
            self.set_text_color(44, 39, 34)
        self._set_body_size(9 if header else 10)
        self.cell(42, 7, label, border=1, fill=True)
        self.multi_cell(0, 7, value, border=1, fill=True)


def markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    font_path = _resolve_cjk_font()
    pdf = _DebatePdf(font_path)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf._set_body_size(11)

    table_header_pending = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.write_paragraph("")
            continue
        if line.startswith("# "):
            pdf.write_title(line[2:].strip())
        elif line.startswith("## "):
            pdf.write_heading(line[3:].strip(), 14, level=2)
        elif line.startswith("### "):
            pdf.write_heading(line[4:].strip(), 12, level=3)
        elif line.startswith("#### "):
            pdf.write_heading(line[5:].strip(), 11, level=4)
        elif line.startswith("- "):
            pdf.write_bullet(line[2:].strip())
        elif line.startswith("> "):
            pdf.write_quote(line[2:].strip())
        elif line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells):
                table_header_pending = False
                continue
            pdf.write_table_row(cells, header=not table_header_pending)
            table_header_pending = True
        else:
            table_header_pending = False
            pdf.write_paragraph(line)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
