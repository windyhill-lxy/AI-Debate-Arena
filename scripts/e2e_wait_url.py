"""等待 HTTP 服务就绪（供 test-e2e.bat 调用）。"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    deadline = time.time() + args.seconds
    while time.time() < deadline:
        if ready(args.url):
            print(f"OK {args.url}")
            return
        time.sleep(1)
    print(f"TIMEOUT {args.url}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
