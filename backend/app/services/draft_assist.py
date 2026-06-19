"""人机模式：代拟发言草稿（可直接填入编辑框）。"""

from collections.abc import AsyncIterator

from app.models import DebateState
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream, resolve_model
from app.services.message_visibility import format_debate_history
from app.services.rag import retrieve_sources


def _draft_messages(debate: DebateState, side: str, hint: str = ""):
    sources = retrieve_sources(debate.topic, hint or debate.topic, debate_id=debate.id)
    side_label = "正方" if side == "affirmative" else "反方"
    source_text = "\n".join(f"- [{s.id}] {s.title}: {s.excerpt}" for s in sources)
    segment = debate.segment_label or debate.phase
    messages = [
        {
            "role": "system",
            "content": (
                f"你是{side_label}辩手，正在「{segment}」环节发言。"
                "请代写一段可直接提交的 Markdown 发言稿（200–450 字）。"
                "必须包含至少一处资料引用，格式为 [kb-xxx]，且编号只能来自下方资料列表。"
                "语气正式、结构清晰，可用小标题或分点。不要输出 JSON 或解释性前后缀。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n"
                f"用户补充要点：{hint or '（无）'}\n"
                f"资料：\n{source_text or '（暂无）'}\n"
                f"近期发言：\n{format_debate_history(debate.messages, viewer_side=side, in_internal_phase=debate.phase in {'opening_prep', 'free_prep', 'closing_prep'}, limit=8)}"
            ),
        },
    ]
    return messages, sources, segment


def _fallback_draft(debate: DebateState, side: str, sources, segment: str) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    cite = sources[0].id if sources else "kb-ai-risk"
    return (
        f"主席好，我方认为在「{debate.topic}」下，{side_label}立场更能回应现实需求。\n\n"
        f"第一，标准应聚焦可验证的学习成效；第二，现有证据显示风险可控 [{cite}]。\n\n"
        f"因此，我方主张……（请根据 `{segment}` 环节补充具体论据。）"
    )


async def generate_draft(debate: DebateState, side: str, hint: str = "") -> dict:
    messages, sources, segment = _draft_messages(debate, side, hint)
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
        text = _fallback_draft(debate, side, sources, segment)

    return {
        "side": side,
        "draft": text,
        "sources": [s.model_dump() for s in sources[:5]],
    }


async def generate_draft_stream_events(debate: DebateState, side: str, hint: str = "") -> AsyncIterator[dict]:
    messages, sources, segment = _draft_messages(debate, side, hint)
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
        draft = (full or "").strip() or _fallback_draft(debate, side, sources, segment)
        yield {"type": "done", "data": {"side": side, "draft": draft, "sources": [s.model_dump() for s in sources[:5]]}}
    except DeepSeekError as exc:
        yield {"type": "error", "message": str(exc)}
        yield {
            "type": "done",
            "data": {
                "side": side,
                "draft": _fallback_draft(debate, side, sources, segment),
                "sources": [s.model_dump() for s in sources[:5]],
            },
        }
