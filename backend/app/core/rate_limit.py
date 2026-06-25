"""Simple in-memory sliding-window rate limits per client IP (API 背压)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_sec: float = 60.0) -> None:
        self.max_events = max_events
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, key: str, *, scope: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window_sec
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= self.max_events:
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁（{scope}），请稍后再试。",
                )
            bucket.append(now)


_create_limiter: SlidingWindowLimiter | None = None
_write_limiter: SlidingWindowLimiter | None = None


def init_rate_limiters(*, create_per_min: int, write_per_min: int) -> None:
    global _create_limiter, _write_limiter
    _create_limiter = SlidingWindowLimiter(max_events=max(1, create_per_min), window_sec=60.0)
    _write_limiter = SlidingWindowLimiter(max_events=max(1, write_per_min), window_sec=60.0)


def client_key(request: Request) -> str:
    if request.client:
        return request.client.host
    return "unknown"


def enforce_create_room_limit(request: Request) -> None:
    if _create_limiter is None:
        return
    _create_limiter.hit(client_key(request), scope="创建房间")


def enforce_write_limit(request: Request) -> None:
    if _write_limiter is None:
        return
    _write_limiter.hit(client_key(request), scope="写操作")
