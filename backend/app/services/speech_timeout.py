from __future__ import annotations

from datetime import datetime

from app.core.time_utils import utc_now
from app.models import DebateState, DebateTiming


def _segment_key(debate: DebateState) -> str:
    return f"{debate.schedule_index}:{debate.segment_label or debate.phase}:{debate.active_speaker_id}"


def mark_user_wait_start(debate: DebateState) -> None:
    if not debate.awaiting_user_since:
        debate.awaiting_user_since = utc_now()


def clear_user_wait(debate: DebateState) -> None:
    debate.awaiting_user_since = None


def apply_timeout_penalty_if_needed(
    debate: DebateState,
    side: str,
    *,
    now: datetime | None = None,
) -> tuple[float, str]:
    if debate.timing != DebateTiming.limited:
        return 0.0, ""
    if not debate.human_timeout_penalty_enabled:
        return 0.0, ""
    if not debate.awaiting_user_since:
        return 0.0, ""
    key = _segment_key(debate)
    if key in debate.timeout_penalty_applied_segments:
        return 0.0, ""

    current = now or utc_now()
    elapsed = (current - debate.awaiting_user_since).total_seconds()
    if elapsed <= max(1, debate.turn_seconds):
        return 0.0, ""

    penalty = abs(float(debate.timeout_penalty_points or 0.5))
    debate.score[side] = debate.score.get(side, 0.0) - penalty
    debate.timeout_penalty_applied_segments.append(key)
    return -penalty, f"人类发言超时 {elapsed:.0f}s，扣 {penalty:.2f} 分"
