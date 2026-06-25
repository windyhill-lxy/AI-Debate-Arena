"""发言可见性：队内讨论与公开发言的信息隔离。"""

from __future__ import annotations

from app.models import DebateMessage

INTERNAL_PREP_PHASES = frozenset({"opening_prep", "free_prep", "closing_prep"})
INTERNAL_LABEL_KEYWORDS = (
    "队内讨论",
    "任务分配",
    "策略锁定",
    "论点分工",
    "论据分配",
    "攻防策略",
    "角色临时分工",
    "总结框架",
    "四辩接收汇总",
)

PUBLIC_DEBATER_PHASES = frozenset({
    "opening_statement",
    "rebuttal",
    "cross_examination",
    "segment_summary",
    "free_debate",
    "closing",
})


def is_internal_message(message: DebateMessage) -> bool:
    """正方/反方在准备环节的队内发言（含任务分配、队内讨论）。"""
    if message.side not in {"affirmative", "negative"}:
        return False
    if message.phase in INTERNAL_PREP_PHASES:
        return True
    label = message.segment_label or ""
    return any(keyword in label for keyword in INTERNAL_LABEL_KEYWORDS)


def is_judge_thought_message(message: DebateMessage) -> bool:
    return (
        message.side == "judge"
        and message.phase == "post_match"
        and "输出裁判报告" not in (message.segment_label or "")
    )


def is_public_message(message: DebateMessage) -> bool:
    if is_internal_message(message) or is_judge_thought_message(message):
        return False

    label = message.segment_label or ""
    if message.side == "judge":
        if "裁判警告" in label:
            return True
        if message.phase == "post_match":
            return "输出裁判报告" in label
        if message.phase == "pre_match":
            return True
        return any(keyword in label for keyword in ("准备就绪", "结束自由辩论", "暂停计时"))

    if message.side in {"affirmative", "negative"}:
        if message.phase:
            return message.phase in PUBLIC_DEBATER_PHASES
        return not any(keyword in label for keyword in INTERNAL_LABEL_KEYWORDS)

    return False


def message_visible_to_side(
    message: DebateMessage,
    viewer_side: str,
    *,
    in_internal_phase: bool,
) -> bool:
    """判断某条历史发言对当前发言方是否可见。"""
    if is_internal_message(message):
        if viewer_side in {"affirmative", "negative"}:
            # 队内讨论仅本方可见
            return message.side == viewer_side
        # 裁判流程节点不读取双方队内密谈
        return False

    if is_judge_thought_message(message):
        return viewer_side in {"judge", "assistant"}

    if is_public_message(message):
        return True

    if message.side == "judge" and message.phase in {
        "argument_review",
        "rebuttal_review",
        "closing_review",
        "free_review",
    }:
        return True

    return False


def filter_messages_for_viewer(
    messages: list[DebateMessage],
    viewer_side: str,
    *,
    in_internal_phase: bool,
) -> list[DebateMessage]:
    return [
        message
        for message in messages
        if message_visible_to_side(message, viewer_side, in_internal_phase=in_internal_phase)
    ]


def format_debate_history(
    messages: list[DebateMessage],
    *,
    viewer_side: str,
    in_internal_phase: bool,
    limit: int = 8,
) -> str:
    visible = filter_messages_for_viewer(messages, viewer_side, in_internal_phase=in_internal_phase)
    lines: list[str] = []
    for message in visible[-limit:]:
        content = (message.content or "").strip()
        if not content:
            continue
        scope = "[队内·仅本方可见]" if is_internal_message(message) else "[公开]"
        lines.append(f"{scope} [{message.side}] {message.speaker_name}: {content}")
    return "\n".join(lines) if lines else "（暂无可见历史发言）"


def latest_message_for_viewer(
    messages: list[DebateMessage],
    side: str,
    viewer_side: str,
    *,
    in_internal_phase: bool,
    public_only: bool = False,
) -> DebateMessage | None:
    for message in reversed(messages):
        if message.side != side:
            continue
        if public_only and not is_public_message(message):
            continue
        if not message_visible_to_side(message, viewer_side, in_internal_phase=in_internal_phase):
            continue
        if (message.content or "").strip():
            return message
    return None


def latest_any_visible_message(
    messages: list[DebateMessage],
    viewer_side: str,
    *,
    in_internal_phase: bool,
) -> DebateMessage | None:
    """当前视角下最近一条可见发言（任意阵营），用于检索查询等。"""
    for message in reversed(messages):
        if not message_visible_to_side(message, viewer_side, in_internal_phase=in_internal_phase):
            continue
        if (message.content or "").strip():
            return message
    return None
