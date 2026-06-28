from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def slide_text(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        names = [
            name
            for name in zf.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        names.sort(key=lambda name: int(re.search(r"(\d+)", name).group(1)))
        slides: list[str] = []
        for name in names:
            root = ET.fromstring(zf.read(name))
            text = "\n".join(node.text for node in root.findall(".//a:t", NS) if node.text)
            slides.append(text)
        return slides


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python tools/check_ppt_original_text_preserved.py <original> <new>", file=sys.stderr)
        return 2
    original_slides = slide_text(Path(sys.argv[1]))
    new_slides = slide_text(Path(sys.argv[2]))
    issues: list[str] = []
    for idx, original in enumerate(original_slides, 1):
        original_c = compact(original)
        new_c = compact(new_slides[idx - 1] if idx - 1 < len(new_slides) else "")
        if original_c and original_c not in new_c:
            issues.append(f"slide {idx}: original text not preserved as a contiguous block")
    if issues:
        print("\n".join(issues))
        return 1
    print("ORIGINAL_TEXT_PRESERVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
