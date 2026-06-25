"""Extract font URLs and font-family usage from Anthropic / Claude pages."""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "assets" / "fonts" / "anthropic"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_urls(text: str) -> set[str]:
    return set(re.findall(r"https?://[^\s\"'<>]+\.(?:woff2|woff|css)", text, re.I))


def main() -> None:
    pages = [
        "https://www.anthropic.com/",
        "https://claude.ai/login",
    ]
    all_urls: set[str] = set()
    css_texts: list[str] = []
    for page in pages:
        print(f"\n=== {page} ===")
        try:
            html = fetch(page)
        except Exception as exc:
            print("fetch failed:", exc)
            continue
        urls = extract_urls(html)
        all_urls |= urls
        for u in sorted(urls):
            print(u)
        css_links = re.findall(r'href="(https?://[^"]+\.css[^"]*)"', html)
        for css_url in css_links[:12]:
            try:
                css = fetch(css_url)
                css_texts.append(css)
                all_urls |= extract_urls(css)
            except Exception as exc:
                print("css failed", css_url, exc)
    print("\n=== font-family in CSS ===")
    families = sorted(set(re.findall(r"font-family:\s*([^;}{]+)", "\n".join(css_texts), re.I)))
    for fam in families[:40]:
        print(fam.strip())
    woff2 = sorted(u for u in all_urls if u.endswith(".woff2"))
    print("\n=== woff2 total", len(woff2), "===")
    for u in woff2:
        print(u)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "manifest.txt"
    manifest.write_text("\n".join(woff2), encoding="utf-8")
    print("\nmanifest ->", manifest)


if __name__ == "__main__":
    main()
