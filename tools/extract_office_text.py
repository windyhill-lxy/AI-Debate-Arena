import re
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


def pptx_text(path: Path) -> None:
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(path) as zf:
        slide_names = [
            name
            for name in zf.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        slide_names.sort(key=lambda name: int(re.search(r"(\d+)", name).group(1)))
        for name in slide_names:
            root = ET.fromstring(zf.read(name))
            texts = [node.text for node in root.findall(".//a:t", ns) if node.text]
            print(f"--- {name} ---")
            print("\n".join(texts))


def docx_text(path: Path) -> None:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    for para in root.findall(".//w:p", ns):
        text = "".join(node.text or "" for node in para.findall(".//w:t", ns))
        if text.strip():
            print(text)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"pptx", "docx"}:
        print("Usage: python tools/extract_office_text.py pptx|docx <path>", file=sys.stderr)
        return 2
    path = Path(sys.argv[2])
    if sys.argv[1] == "pptx":
        pptx_text(path)
    else:
        docx_text(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
