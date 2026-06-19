"""用 Python 托管 frontend/dist（E2E / 无 Node 开发服务器时使用）。"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "frontend" / "dist",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "index.html").is_file():
        raise SystemExit(f"缺少 {root / 'index.html'}，请先运行 setup-e2e.bat 构建前端，或 start.bat 启动开发服。")

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

    with socketserver.TCPServer(("127.0.0.1", args.port), SPAHandler) as httpd:
        print(f"Serving {root} at http://127.0.0.1:{args.port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
