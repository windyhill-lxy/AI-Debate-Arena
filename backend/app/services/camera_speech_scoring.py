from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import DebateState

SHRUG_BONUS = 0.2
POINTING_PENALTY = 0.25
MAX_ABS_DELTA = 0.8


def _iter_samples(path: str, *, since_ts: float | None = None, until_ts: float | None = None):
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = float(row.get("ts") or 0)
        if since_ts is not None and ts < since_ts:
            continue
        if until_ts is not None and ts > until_ts:
            continue
        yield row


def camera_speech_delta(
    session_log_path: str,
    *,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> tuple[float, str]:
    events = [row.get("gesture_event") for row in _iter_samples(session_log_path, since_ts=since_ts, until_ts=until_ts) or []]
    if not events:
        return 0.0, ""
    shrug_count = events.count("shrug")
    pointing_count = events.count("pointing")
    delta = shrug_count * SHRUG_BONUS - pointing_count * POINTING_PENALTY
    delta = max(-MAX_ABS_DELTA, min(MAX_ABS_DELTA, delta))
    if not delta:
        return 0.0, ""
    parts: list[str] = []
    if shrug_count:
        parts.append(f"摊手表达自然 +{shrug_count * SHRUG_BONUS:.2f}")
    if pointing_count:
        parts.append(f"手指指人 {pointing_count} 次 -{pointing_count * POINTING_PENALTY:.2f}")
    return round(delta, 2), "；".join(parts)


def apply_camera_speech_score(
    debate: DebateState,
    side: str,
    session_log_path: str,
    *,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> tuple[float, str]:
    delta, reason = camera_speech_delta(session_log_path, since_ts=since_ts, until_ts=until_ts)
    if not delta:
        return 0.0, ""
    debate.score[side] = debate.score.get(side, 0.0) + delta
    return delta, reason
