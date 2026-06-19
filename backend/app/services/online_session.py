"""联机会话：主人创建房间前，客人可通过 session 链接等待。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

_sessions: dict[str, dict[str, object]] = {}


def create_session() -> str:
    session_id = uuid4().hex[:12]
    _sessions[session_id] = {
        "session_id": session_id,
        "debate_id": None,
        "topic": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return session_id


def link_session(session_id: str, debate_id: str, topic: str) -> bool:
    entry = _sessions.get(session_id)
    if entry is None:
        return False
    entry["debate_id"] = debate_id
    entry["topic"] = topic
    return True


def get_session(session_id: str) -> dict[str, object] | None:
    entry = _sessions.get(session_id)
    return dict(entry) if entry else None
