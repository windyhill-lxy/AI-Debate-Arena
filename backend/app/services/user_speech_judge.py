"""裁判大模型审核用户发言质量（替代简单规则拦截）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models import DebateState, UserMessageCreate
from app.services.llm import chat_completion, extract_json_block, resolve_model
from app.services.message_visibility import format_debate_history, latest_message_for_viewer
from app.services.ops_events import append_ops_event

logger = logging.getLogger(__name__)


@dataclass
class UserSpeechReview:
    acceptable: bool
    reason: str = ""
    penalty: float = 0.5
    judge_comment: str = ""
    teammate_comment: str = ""


def _build_review_messages(
    debate: DebateState,
    payload: UserMessageCreate,
    *,
    public_debate: bool,
) -> list[dict[str, str]]:
    side_label = "正方" if payload.side == "affirmative" else "反方"
    opp_side = "negative" if payload.side == "affirmative" else "affirmative"
    in_internal = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
    last_opp = latest_message_for_viewer(
        debate.messages,
        opp_side,
        payload.side,
        in_internal_phase=in_internal,
        public_only=public_debate,
    )
    history = format_debate_history(
        debate.messages,
        viewer_side="judge",
        in_internal_phase=in_internal,
        limit=10,
    )
    context_type = "公开发言环节" if public_debate else "队内讨论/任务分配环节"

    return [
        {
            "role": "system",
            "content": (
                "你是辩论赛主裁判，只负责审核辩手刚提交的发言是否有效，不写稿、不站队。"
                "无效发言包括但不限于：乱码灌水、与辩题无关、纯情绪发泄、复制粘贴无意义文本、"
                "只有附和没有论点、明显未回应当前环节要求、故意捣乱。"
                "有效发言：即使论证较弱，只要围绕辩题表达清晰观点/回应/任务分工，就应放行。"
                "输出严格 JSON，不要 Markdown 代码块："
                '{"acceptable": true/false, "reason": "20字内问题摘要", '
                '"penalty": 0.5, "judge_comment": "公开发言无效时的裁判警告全文（80-160字）", '
                '"teammate_comment": "队内讨论无效时的队友提醒全文（60-120字）"}'
                "acceptable 为 false 时：公开发言 penalty 取 0.3~1.0（严重捣乱可 1.0）；"
                "队内讨论 penalty 固定为 0。judge_comment / teammate_comment 二选一填写。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n"
                f"当前环节：{debate.segment_label}（{debate.phase}）\n"
                f"审核类型：{context_type}\n"
                f"发言方：{side_label} · {payload.speaker_name}\n"
                f"对方最近可见发言：{(last_opp.content[:500] if last_opp else '（暂无）')}\n"
                f"近期可见历史：\n{history}\n\n"
                f"待审核发言：\n{payload.content}"
            ),
        },
    ]


def _parse_review(raw: str, *, public_debate: bool) -> UserSpeechReview:
    parsed = extract_json_block(raw)
    acceptable = bool(parsed.get("acceptable", True))
    reason = str(parsed.get("reason") or "").strip()
    try:
        penalty = float(parsed.get("penalty", 0.5))
    except (TypeError, ValueError):
        penalty = 0.5
    penalty = max(0.3, min(1.0, penalty)) if public_debate else 0.0
    judge_comment = str(parsed.get("judge_comment") or "").strip()
    teammate_comment = str(parsed.get("teammate_comment") or "").strip()
    return UserSpeechReview(
        acceptable=acceptable,
        reason=reason,
        penalty=penalty,
        judge_comment=judge_comment,
        teammate_comment=teammate_comment,
    )


async def review_user_speech(
    debate: DebateState,
    payload: UserMessageCreate,
    *,
    public_debate: bool,
) -> UserSpeechReview:
    messages = _build_review_messages(debate, payload, public_debate=public_debate)
    try:
        raw = await chat_completion(
            messages,
            model=resolve_model(phase=debate.phase, speaker_id="judge"),
            temperature=0.2,
            debate_id=debate.id,
            operation="user_speech_review",
        )
        return _parse_review(raw, public_debate=public_debate)
    except Exception as exc:
        logger.warning("user speech review failed: %s", exc)
        append_ops_event("user_speech_review_failed", str(exc), debate_id=debate.id)
        return UserSpeechReview(acceptable=True, reason="裁判审核暂不可用，已放行")
