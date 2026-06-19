"""赛程元数据：哪些环节需要完整 LLM 公开发言。"""

from app.core.time_utils import utc_now
from app.models import DebateState, build_schedule_status
from app.services.debate_schedule import advance_schedule, get_segment


def is_procedural_segment(debate: DebateState) -> bool:
    """裁判侧流程/检索/判断环节：不生成主舞台长发言，仅推进赛程。"""
    segment = get_segment(debate, debate.schedule_index)
    if segment is None or segment.speaker_side != "judge":
        return False
    label = segment.label or ""
    if segment.phase == "pre_match":
        return False
    if segment.phase == "post_match" and "输出裁判报告" in label:
        return False
    return True


def advance_procedural_turn(debate: DebateState) -> DebateState:
    """裁判流程环节：仅推进赛程，不写入发言。"""
    debate.turn_index += 1
    advance_schedule(debate)
    debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)
    debate.updated_at = utc_now()
    return debate


def schedule_progress(debate: DebateState) -> tuple[int, int]:
    from app.services.schedule_config import load_schedule

    template = getattr(debate, "schedule_template", None) or "formal_4v4"
    total = len(load_schedule(template))
    current = min(debate.schedule_index + 1, total) if debate.phase != "finished" else total
    return current, total
