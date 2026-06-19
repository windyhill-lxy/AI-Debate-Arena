import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None
_memory_cache: dict[str, Any] = {}


async def connect_redis() -> None:
    global _redis
    _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await _redis.ping()
    except Exception:
        _redis = None


def redis_connected() -> bool:
    return _redis is not None


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    if _redis is None:
        _memory_cache[key] = value
        return
    await _redis.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)


async def cache_get(key: str) -> Any | None:
    if _redis is None:
        return _memory_cache.get(key)
    raw = await _redis.get(key)
    return json.loads(raw) if raw else None


async def cache_publish(channel: str, payload: Any) -> None:
    if _redis is not None:
        await _redis.publish(channel, json.dumps(payload, ensure_ascii=False, default=str))
