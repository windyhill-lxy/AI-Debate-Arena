from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any


def _events_file() -> Path:
    root = Path(__file__).resolve().parents[3]
    p = root / "data" / "ops_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_ops_event(event_type: str, message: str, **extra: Any) -> None:
    row = {"ts": time(), "event_type": event_type, "message": message, **extra}
    try:
        with _events_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def list_recent_ops_events(limit: int = 80) -> list[dict[str, Any]]:
    p = _events_file()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-max(1, min(limit, 300)) :]
