"""管理端：房间概览、列表与运行态诊断。"""

from __future__ import annotations

from typing import Any

from app.db.mongo import list_debates, list_debates_in_progress, storage_mode
from app.db.redis_cache import redis_connected
from app.models import DebateState
from app.services.auto_runner import active_runner_status
from app.services.llm_usage import get_debate_llm_stats
from app.services.ops_events import list_recent_ops_events


def _summarize(doc: dict[str, Any]) -> dict[str, Any]:
    debate = DebateState.model_validate(doc)
    return {
        "id": debate.id,
        "topic": debate.topic,
        "mode": debate.mode.value,
        "phase": debate.phase,
        "segment_label": debate.segment_label,
        "schedule_index": debate.schedule_index,
        "schedule_template": debate.schedule_template,
        "auto_running": debate.auto_running,
        "awaiting_user": debate.awaiting_user,
        "message_count": len(debate.messages),
        "turn_index": debate.turn_index,
        "score": debate.score,
        "updated_at": debate.updated_at.isoformat() if debate.updated_at else None,
        "created_at": debate.created_at.isoformat() if debate.created_at else None,
    }


async def admin_overview() -> dict[str, Any]:
    from app.core.config import get_settings
    from app.db.mongo import database

    settings = get_settings()
    all_docs = await list_debates()
    in_progress = await list_debates_in_progress()

    counts = {
        "total": len(all_docs),
        "in_progress": 0,
        "finished": 0,
        "awaiting_user": 0,
        "auto_running": 0,
    }
    for doc in all_docs:
        phase = doc.get("phase")
        if phase == "finished":
            counts["finished"] += 1
        else:
            counts["in_progress"] += 1
        if doc.get("awaiting_user"):
            counts["awaiting_user"] += 1
        if doc.get("auto_running"):
            counts["auto_running"] += 1

    runners = active_runner_status()

    return {
        "storage": storage_mode(),
        "mongo_connected": database() is not None,
        "redis_connected": redis_connected(),
        "deepseek_configured": bool(settings.deepseek_api_key),
        "aliyun_tts_enabled": settings.aliyun_tts_enabled,
        "debate_counts": counts,
        "active_runners": runners,
        "in_progress_ids": [d.get("id") for d in in_progress[:20]],
        "ops_events": list_recent_ops_events(limit=30),
    }


async def admin_list_debates(*, limit: int = 50) -> list[dict[str, Any]]:
    docs = await list_debates()
    docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return [_summarize(d) for d in docs[: max(1, min(limit, 100))]]


async def admin_debate_detail(debate_id: str) -> dict[str, Any] | None:
    from app.db.mongo import get_debate

    doc = await get_debate(debate_id)
    if doc is None:
        return None
    llm_stats = await get_debate_llm_stats(debate_id)
    runners = active_runner_status()
    summary = _summarize(doc)
    last_error = None
    messages = doc.get("messages") or []
    if messages:
        last = messages[-1]
        if "模型暂不可用" in (last.get("content") or ""):
            last_error = "recent_message_reports_llm_unavailable"
    return {
        "summary": summary,
        "llm_stats": llm_stats,
        "runner": runners.get(debate_id),
        "last_message_preview": (messages[-1].get("content") or "")[:240] if messages else "",
        "diagnostics": {
            "stale_auto_flag": bool(doc.get("auto_running") and debate_id not in runners),
            "runner_alive": debate_id in runners,
            "last_error_hint": last_error,
        },
        "ops_events": list_recent_ops_events(limit=50),
    }
