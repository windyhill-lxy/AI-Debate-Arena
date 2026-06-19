"""使用记录：每次创建辩论房间时追加一行 JSONL，供 Admin 面板读取统计。"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.time_utils import utc_now

_LOG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "usage_log.jsonl"


def record_debate_created(debate_id: str, topic: str, mode: str) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": utc_now().isoformat(),
        "debate_id": debate_id,
        "topic": topic,
        "mode": mode,
    }
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_usage_log(limit: int = 20) -> dict:
    if not _LOG_PATH.exists():
        return {"total": 0, "recent": []}
    lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    total = len(lines)
    recent = []
    for line in reversed(lines[-limit:]):
        try:
            recent.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return {"total": total, "recent": recent}
