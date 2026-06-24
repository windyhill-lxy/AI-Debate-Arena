"""人机模式：代拟发言草稿（可直接填入编辑框）。"""

from collections.abc import AsyncIterator

from app.models import DebateState
from app.services.ai_context_manager import format_argument_bank
from app.services.argument_bank import normalize_argument_citations, primary_argument_id_for_side
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream, resolve_model
from app.services.message_visibility import format_debate_history
from app.services.rag import retrieve_sources


INTERNAL_PREP_PHASES = {"opening_prep", "free_prep", "closing_prep"}
POSITION_LABELS = {1: "一辩", 2: "二辩", 3: "三辩", 4: "四辩"}


def _effective_position(debate: DebateState, side: str, position: int = 1) -> int:
    if debate.user_side == side and debate.user_position:
        return debate.user_position
    return min(max(position or 1, 1), 4)


def _role_label(side: str, position: int) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    return f"{side_label}{POSITION_LABELS.get(position, f'{position}辩')}"


def _background_sources_text(sources) -> str:
    return "\n".join(f"- {s.title}: {s.excerpt}" for s in sources) or "（暂无额外背景资料）"


def _phase_instruction(debate: DebateState) -> str:
    segment = debate.segment_label or debate.phase
    if debate.phase in INTERNAL_PREP_PHASES or "队内讨论" in segment:
        return (
            "这是队内讨论，不是正式立论、驳论或陈词；只写当前席位本人要对队友说的一段话。"
            "不要称呼主席、评委、对方辩友，不要写开场白，不要输出完整一辩立论结构。"
            "重点是说明如何利用论据库、如何衔接队友分工和下一步策略。"
        )
    return "这是公开发言草稿；必须符合当前席位与当前环节，不要串到其他辩位任务。"


def _draft_messages(debate: DebateState, side: str, hint: str = "", position: int = 1):
    sources = retrieve_sources(debate.topic, hint or debate.topic, debate_id=debate.id)
    effective_position = _effective_position(debate, side, position)
    role = _role_label(side, effective_position)
    argument_text = format_argument_bank(debate.argument_bank.get(side, []))
    fallback_id = primary_argument_id_for_side(debate, side, effective_position)
    segment = debate.segment_label or debate.phase
    in_internal = debate.phase in INTERNAL_PREP_PHASES
    messages = [
        {
            "role": "system",
            "content": (
                f"你正在为用户代拟草稿。用户席位是{role}，当前环节是「{segment}」。"
                f"{_phase_instruction(debate)}"
                "请输出一段可直接提交的 Markdown 发言稿，120 到 320 字。"
                "所有知识性事实、数据、研究、案例都只能来自本方论据库。"
                f"引用资料时只能使用本方论据库 ID，例如 [{fallback_id}]；不得使用任何非本方论据库编号或资料标题代替 ID。"
                f"必须至少包含一个本方论据库 ID，且只能使用 {('AFF' if side == 'affirmative' else 'NEG')}-数字格式。"
                "不要输出 JSON 或解释性前后缀。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n"
                f"用户席位：{role}\n"
                f"当前环节：{segment}\n"
                f"用户补充要点：{hint or '（无）'}\n"
                f"本方论据库（唯一可引用编号来源）：\n{argument_text}\n"
                f"额外背景（只帮助理解，不得引用其中编号）：\n{_background_sources_text(sources)}\n"
                f"近期发言：\n{format_debate_history(debate.messages, viewer_side=side, in_internal_phase=in_internal, limit=8)}"
            ),
        },
    ]
    return messages, sources, segment


def _fallback_draft(debate: DebateState, side: str, sources, segment: str, position: int = 1) -> str:
    effective_position = _effective_position(debate, side, position)
    role = _role_label(side, effective_position)
    cite = primary_argument_id_for_side(debate, side, effective_position)
    if debate.phase in INTERNAL_PREP_PHASES or "队内讨论" in (segment or ""):
        return (
            f"{role}：我这一段不写成正式立论，先把论据怎么用讲清楚。"
            f"我会围绕 [{cite}] 做一个可落地的支撑点，说明它和本方标准之间的关系，"
            "再把对方可能质疑的样本边界留给后续攻防。队友发言时可以顺着这个编号继续补强。"
        )
    return (
        f"{role}发言：我方围绕「{debate.topic}」推进当前环节。"
        f"核心事实先落在 [{cite}]，再把它转化为比较标准：哪一方更能解释真实学习效果、风险边界和可操作路径。"
        f"因此本轮重点不是空泛判断，而是用论据库中的材料完成回应与推进。"
    )


async def generate_draft(debate: DebateState, side: str, hint: str = "", position: int = 1) -> dict:
    effective_position = _effective_position(debate, side, position)
    messages, sources, segment = _draft_messages(debate, side, hint, effective_position)
    try:
        draft = await chat_completion(
            messages,
            model=resolve_model(phase=debate.phase),
            temperature=0.75,
            debate_id=debate.id,
            operation="assist_draft",
        )
        text = (draft or "").strip()
        if not text:
            raise ValueError("empty draft")
    except (DeepSeekError, ValueError):
        text = _fallback_draft(debate, side, sources, segment, effective_position)
    text = normalize_argument_citations(text, debate, side, position=effective_position)

    return {
        "side": side,
        "position": effective_position,
        "draft": text,
        "sources": [s.model_dump() for s in sources[:5]],
    }


async def generate_draft_stream_events(debate: DebateState, side: str, hint: str = "", position: int = 1) -> AsyncIterator[dict]:
    effective_position = _effective_position(debate, side, position)
    messages, sources, segment = _draft_messages(debate, side, hint, effective_position)
    full = ""
    try:
        async for chunk in chat_completion_stream(
            messages,
            model=resolve_model(phase=debate.phase),
            temperature=0.75,
            debate_id=debate.id,
            operation="assist_draft_stream",
        ):
            full += chunk
            yield {"type": "chunk", "text": chunk, "full_text": full}
        draft = (full or "").strip() or _fallback_draft(debate, side, sources, segment, effective_position)
        draft = normalize_argument_citations(draft, debate, side, position=effective_position)
        yield {
            "type": "done",
            "data": {"side": side, "position": effective_position, "draft": draft, "sources": [s.model_dump() for s in sources[:5]]},
        }
    except DeepSeekError as exc:
        yield {"type": "error", "message": str(exc)}
        fallback = normalize_argument_citations(
            _fallback_draft(debate, side, sources, segment, effective_position),
            debate,
            side,
            position=effective_position,
        )
        yield {
            "type": "done",
            "data": {
                "side": side,
                "position": effective_position,
                "draft": fallback,
                "sources": [s.model_dump() for s in sources[:5]],
            },
        }
