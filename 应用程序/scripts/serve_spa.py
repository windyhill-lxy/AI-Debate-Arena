"""托管打包版 frontend/dist，支持本机与局域网访问。"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "frontend-dist",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "index.html").is_file():
        raise SystemExit(f"缺少 {root / 'index.html'}，请先运行「准备程序.bat」。")

    os.chdir(root)
    handler = http.server.SimpleHTTPRequestHandler

    class SPAHandler(handler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            file_path = root / path.lstrip("/")
            if path != "/" and file_path.is_file():
                return super().do_GET()
            self.path = "/index.html"
            return super().do_GET()

    with socketserver.TCPServer((args.host, args.port), SPAHandler) as httpd:
        print(f"Serving {root} at http://{args.host}:{args.port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
