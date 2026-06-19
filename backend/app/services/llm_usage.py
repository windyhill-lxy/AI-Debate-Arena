"""Per-debate LLM 调用与 token 用量聚合（内存，便于成本估算与排障）。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _DebateStats:
    total_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    operations: dict[str, int] = field(default_factory=dict)


_lock = asyncio.Lock()
_stats: dict[str, _DebateStats] = {}


async def record_llm_call(
    debate_id: str | None,
    *,
    operation: str,
    model: str,
    duration_ms: float,
    prompt_tokens: int,
    completion_tokens: int,
    ok: bool,
) -> None:
    if not debate_id:
        return
    async with _lock:
        s = _stats.setdefault(debate_id, _DebateStats())
        s.total_calls += 1
        s.operations[operation] = s.operations.get(operation, 0) + 1
        s.total_duration_ms += duration_ms
        if ok:
            s.prompt_tokens += prompt_tokens
            s.completion_tokens += completion_tokens
        else:
            s.failed_calls += 1


async def get_debate_llm_stats(debate_id: str) -> dict[str, Any]:
    async with _lock:
        s = _stats.get(debate_id)
        if not s:
            return {
                "debate_id": debate_id,
                "total_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "failed_calls": 0,
                "total_duration_ms": 0.0,
                "operations": {},
            }
        return {
            "debate_id": debate_id,
            "total_calls": s.total_calls,
            "prompt_tokens": s.prompt_tokens,
            "completion_tokens": s.completion_tokens,
            "failed_calls": s.failed_calls,
            "total_duration_ms": round(s.total_duration_ms, 1),
            "operations": dict(s.operations),
            "note": "内存聚合，进程重启后清零；用于粗略成本与性能观测。",
        }
