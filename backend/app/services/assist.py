from collections.abc import AsyncIterator

from app.models import DebateState
from app.services.ai_context_manager import format_argument_bank
from app.services.argument_bank import normalize_argument_citations, primary_argument_id_for_side, referenced_argument_ids
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream, extract_json_block, resolve_model
from app.services.message_visibility import format_debate_history, latest_message_for_viewer
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


def _sources_from_argument_bank(debate: DebateState | None, side: str, ids: set[str] | None = None) -> list[dict]:
    if debate is None or side not in {"affirmative", "negative"}:
        return []
    items = debate.argument_bank.get(side, [])
    if ids:
        items = [item for item in items if item.id in ids]
    return [
        {
            "id": item.id,
            "title": item.title or item.id,
            "excerpt": item.claim,
            "reliability": 0.85,
        }
        for item in items[:4]
    ]


def _background_sources_text(sources) -> str:
    return "\n".join(f"- {s.title}: {s.excerpt}" for s in sources) or "（暂无额外背景资料）"


def _assist_messages(debate: DebateState, side: str, draft: str, position: int = 1):
    sources = retrieve_sources(debate.topic, draft or debate.topic, debate_id=debate.id)
    effective_position = _effective_position(debate, side, position)
    role = _role_label(side, effective_position)
    argument_text = format_argument_bank(debate.argument_bank.get(side, []))
    fallback_id = primary_argument_id_for_side(debate, side, effective_position)
    prefix = "AFF" if side == "affirmative" else "NEG"
    opp_side = "negative" if side == "affirmative" else "affirmative"
    in_internal = debate.phase in INTERNAL_PREP_PHASES
    last_opp_msg = latest_message_for_viewer(
        debate.messages,
        opp_side,
        side,
        in_internal_phase=in_internal,
        public_only=True,
    )
    last_opp = (last_opp_msg.content[:600] if last_opp_msg else "")

    messages = [
        {
            "role": "system",
            "content": (
                f"你是{role}的发言教练，只给用户思路，不代替用户写全文。"
                "所有建议、追问句和草稿提示引用资料时，只能使用本方论据库 ID。"
                f"编号格式必须是 [{fallback_id}] 这样的 AFF-数字或 NEG-数字；严禁使用任何非本方论据库编号。"
                "如果当前是队内讨论，只给队内策略建议，不要改成正式立论陈词。"
                '输出 JSON：{"suggestion":"Markdown 三段式思路",'
                '"counter_rebuttal":"针对对方上一句的反驳切口（80字内）",'
                f'"possible_lines":["带 [{prefix}-1] 这类本方论据 ID 的可追问句", "...", "..."],'
                f'"cite_ids":["{fallback_id}"]}}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n用户席位：{role}\n当前环节：{debate.segment_label or debate.phase}\n"
                f"用户草稿：{draft or '（暂无）'}\n"
                f"对方上一段发言：{last_opp or '（暂无）'}\n"
                f"本方论据库（唯一可引用编号来源）：\n{argument_text}\n"
                f"额外背景（只帮助理解，不得引用其中编号）：\n{_background_sources_text(sources)}\n"
                f"历史：\n{format_debate_history(debate.messages, viewer_side=side, in_internal_phase=in_internal)}"
            ),
        },
    ]
    return messages, sources


def _fallback_assist(side: str, sources, debate: DebateState | None = None, position: int = 1) -> dict:
    side_label = "正方" if side == "affirmative" else "反方"
    cite = primary_argument_id_for_side(debate, side, position) if debate else f"{'AFF' if side == 'affirmative' else 'NEG'}-{max(position, 1)}"
    return {
        "side": side,
        "suggestion": (
            f"{side_label}可先承认对方合理点，再把争点拉回标准、证据与影响范围。"
            f"建议用三段式：定义概念、给出依据 [{cite}]、指出论证缺口。"
        ),
        "counter_rebuttal": "追问对方是否把个案当成总体趋势，并要求可验证样本范围。",
        "possible_lines": [
            f"请问对方如何回应 [{cite}] 对本方标准的支撑？",
            "对方标准是否前后一致？",
            "请给出可复现的数据来源。",
        ],
        "sources": _sources_from_argument_bank(debate, side, {cite}) if debate else [],
    }


def _parse_assist(raw: str, side: str, sources, debate: DebateState | None = None, position: int = 1) -> dict:
    parsed = extract_json_block(raw)
    suggestion = normalize_argument_citations(parsed.get("suggestion", raw), debate, side, position=position) if debate else parsed.get("suggestion", raw)
    counter_rebuttal = (
        normalize_argument_citations(parsed.get("counter_rebuttal", ""), debate, side, position=position)
        if debate
        else parsed.get("counter_rebuttal", "")
    )
    possible_lines = [
        normalize_argument_citations(line, debate, side, position=position) if debate else line
        for line in (parsed.get("possible_lines") or [])
    ]
    cite_ids = {item.upper() for item in parsed.get("cite_ids") or [] if isinstance(item, str)}
    cite_ids |= referenced_argument_ids(suggestion)
    cite_ids |= referenced_argument_ids(counter_rebuttal)
    for line in possible_lines:
        cite_ids |= referenced_argument_ids(line)
    return {
        "side": side,
        "position": position,
        "suggestion": suggestion,
        "counter_rebuttal": counter_rebuttal,
        "possible_lines": possible_lines,
        "sources": _sources_from_argument_bank(debate, side, cite_ids) if debate else [source.model_dump() for source in sources[:2]],
    }


async def generate_assist(debate: DebateState, side: str, draft: str, position: int = 1) -> dict:
    effective_position = _effective_position(debate, side, position)
    messages, sources = _assist_messages(debate, side, draft, effective_position)
    try:
        raw = await chat_completion(
            messages,
            model=resolve_model(phase=debate.phase),
            temperature=0.7,
            debate_id=debate.id,
            operation="assist",
        )
        return _parse_assist(raw, side, sources, debate, effective_position)
    except (DeepSeekError, ValueError, KeyError):
        return _fallback_assist(side, sources, debate, effective_position)


async def generate_assist_stream_events(debate: DebateState, side: str, draft: str, position: int = 1) -> AsyncIterator[dict]:
    effective_position = _effective_position(debate, side, position)
    messages, sources = _assist_messages(debate, side, draft, effective_position)
    raw = ""
    try:
        async for chunk in chat_completion_stream(
            messages,
            model=resolve_model(phase=debate.phase),
            temperature=0.7,
            debate_id=debate.id,
            operation="assist_stream",
        ):
            raw += chunk
            yield {"type": "chunk", "text": chunk, "full_text": raw}
        try:
            result = _parse_assist(raw, side, sources, debate, effective_position)
        except Exception:
            result = _fallback_assist(side, sources, debate, effective_position)
        yield {"type": "done", "data": result}
    except DeepSeekError as exc:
        yield {"type": "error", "message": str(exc)}
        yield {"type": "done", "data": _fallback_assist(side, sources, debate, effective_position)}
