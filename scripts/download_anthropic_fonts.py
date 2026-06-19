"""Download Anthropic brand fonts listed in manifest.txt."""
from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "frontend" / "src" / "assets" / "fonts" / "anthropic"
MANIFEST = FONT_DIR / "manifest.txt"


def main() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    urls = [line.strip() for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    for url in urls:
        name = url.rsplit("_", 1)[-1]
        if not name.endswith(".woff2"):
            name = url.rsplit("/", 1)[-1]
        dest = FONT_DIR / name
        if dest.exists() and dest.stat().st_size > 1000:
            print("skip", dest.name)
            continue
        print("download", dest.name)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())


if __name__ == "__main__":
    main()
