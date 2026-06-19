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

    def _set_body_size(self, size: float = 11) -> None:
        self.set_font(self._font_name, size=size)

    def write_heading(self, text: str, size: float) -> None:
        self._set_body_size(size)
        self.multi_cell(0, size * 0.45, _strip_inline_md(text))
        self.ln(2)

    def write_paragraph(self, text: str) -> None:
        if not text.strip():
            self.ln(3)
            return
        self._set_body_size(11)
        self.multi_cell(0, 6, _strip_inline_md(text))
        self.ln(1)


def markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    font_path = _resolve_cjk_font()
    pdf = _DebatePdf(font_path)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf._set_body_size(11)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.write_paragraph("")
            continue
        if line.startswith("# "):
            pdf.write_heading(line[2:].strip(), 16)
        elif line.startswith("## "):
            pdf.write_heading(line[3:].strip(), 14)
        elif line.startswith("### "):
            pdf.write_heading(line[4:].strip(), 12)
        elif line.startswith("- "):
            pdf.write_paragraph(f"• {line[2:].strip()}")
        else:
            pdf.write_paragraph(line)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
