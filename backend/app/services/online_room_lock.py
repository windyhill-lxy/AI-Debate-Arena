from __future__ import annotations

import asyncio

_online_room_locks: dict[str, asyncio.Lock] = {}


def online_room_lock(debate_id: str) -> asyncio.Lock:
    lock = _online_room_locks.get(debate_id)
    if lock is None:
        lock = asyncio.Lock()
        _online_room_locks[debate_id] = lock
    return lock
