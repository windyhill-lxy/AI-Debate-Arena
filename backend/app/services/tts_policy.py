from app.core.config import get_settings
from app.models import DebateMessage, DebateState


def _enabled_phases() -> set[str]:
    raw = get_settings().tts_phases.strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def should_synthesize_tts(debate: DebateState, message: DebateMessage) -> bool:
    settings = get_settings()
    if not settings.aliyun_tts_enabled:
        return False
    if not debate.tts_enabled:
        return False
    if message.phase in {"opening_prep", "free_prep", "closing_prep"}:
        return False
    label = message.segment_label or ""
    if message.side == "judge":
        return (
            message.phase == "pre_match"
            or message.phase == "post_match"
            or "裁判警告" in label
            or "输出裁判报告" in label
        )
    if message.phase in _enabled_phases():
        return True
    return False
