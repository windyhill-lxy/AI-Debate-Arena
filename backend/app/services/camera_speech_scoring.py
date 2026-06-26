from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import DebateState
from app.services.visual_behavior_analysis import summarize_visual_samples

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
    samples = list(_iter_samples(session_log_path, since_ts=since_ts, until_ts=until_ts) or [])
    if not samples:
        return 0.0, ""
    summary = summarize_visual_samples(samples)
    delta = max(-MAX_ABS_DELTA, min(MAX_ABS_DELTA, summary.score_delta))
    if not delta:
        return 0.0, summary.short_summary()
    reason_parts = [summary.short_summary()]
    if summary.score_reason:
        reason_parts.append(summary.score_reason)
    reason_parts.append(f"对方策略建议：{summary.opponent_strategy_hint}")
    return round(delta, 2), "；".join(reason_parts)


def apply_camera_speech_score(
    debate: DebateState,
    side: str,
    session_log_path: str,
    *,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> tuple[float, str]:
    delta, reason = camera_speech_delta(session_log_path, since_ts=since_ts, until_ts=until_ts)
    samples = list(_iter_samples(session_log_path, since_ts=since_ts, until_ts=until_ts) or [])
    summary = summarize_visual_samples(samples)
    if summary.sample_count:
        opponent_side = "negative" if side == "affirmative" else "affirmative"
        debate.camera_strategy_hints[opponent_side] = {
            "mode": summary.strategy_mode,
            "hint": summary.opponent_strategy_hint,
            "summary": summary.short_summary(),
            "dimensions": summary.dimensions,
            "gesture_counts": summary.gesture_counts,
            "delivery": summary.delivery,
            "emotion": summary.emotion,
            "confidence_label": summary.confidence_label,
            "score_delta": summary.score_delta,
        }
    if not delta:
        return 0.0, reason if summary.sample_count else ""
    debate.score[side] = debate.score.get(side, 0.0) + delta
    return delta, reason
