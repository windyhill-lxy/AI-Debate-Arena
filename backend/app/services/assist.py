from collections.abc import AsyncIterator

from app.models import DebateState
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream, extract_json_block, resolve_model
from app.services.message_visibility import format_debate_history, latest_message_for_viewer
from app.services.rag import retrieve_sources


def _assist_messages(debate: DebateState, side: str, draft: str):
    sources = retrieve_sources(debate.topic, draft or debate.topic, debate_id=debate.id)
    side_label = "正方" if side == "affirmative" else "反方"
    source_text = "\n".join(f"- [{s.id}] {s.title}: {s.excerpt}" for s in sources)
    opp_side = "negative" if side == "affirmative" else "affirmative"
    in_internal = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
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
                "你是发言教练，只给用户思路，不代替用户写全文。"
                "资料行首 [id] 为可引用编号，建议中只能使用已列出的编号。"
                '输出 JSON：{"suggestion":"Markdown 三段式思路",'
                '"counter_rebuttal":"针对对方上一句的反驳切口（80字内）",'
                '"possible_lines":["带 [资料编号] 的可追问句", "...", "..."],'
                '"cite_ids":["kb-xxx"]}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{debate.topic}\n用户立场：{side_label}\n"
                f"用户草稿：{draft or '（暂无）'}\n"
                f"对方上一段发言：{last_opp or '（暂无）'}\n"
                f"资料：\n{source_text}\n"
                f"历史：\n{format_debate_history(debate.messages, viewer_side=side, in_internal_phase=in_internal)}"
            ),
        },
    ]
    return messages, sources


def _fallback_assist(side: str, sources) -> dict:
    side_label = "正方" if side == "affirmative" else "反方"
    return {
        "side": side,
        "suggestion": (
            f"{side_label}可先承认对方合理点，再把争点拉回标准、证据与影响范围。"
            "建议用三段式：定义概念、给出依据、指出论证缺口。"
        ),
        "counter_rebuttal": "追问对方是否把个案当成总体趋势，并要求可验证样本范围。",
        "possible_lines": [
            f"请问对方如何回应 [{sources[0].id if sources else 'kb-ai-risk'}] 中的风险证据？",
            "对方标准是否前后一致？",
            "请给出可复现的数据来源。",
        ],
        "sources": [source.model_dump() for source in sources[:3]],
    }


def _parse_assist(raw: str, side: str, sources) -> dict:
    parsed = extract_json_block(raw)
    cite_ids = parsed.get("cite_ids") or []
    cited = [s for s in sources if s.id in cite_ids] or sources[:2]
    return {
        "side": side,
        "suggestion": parsed.get("suggestion", raw),
        "counter_rebuttal": parsed.get("counter_rebuttal", ""),
        "possible_lines": parsed.get("possible_lines", []),
        "sources": [source.model_dump() for source in cited],
    }


async def generate_assist(debate: DebateState, side: str, draft: str) -> dict:
    messages, sources = _assist_messages(debate, side, draft)
    try:
        raw = await chat_completion(
            messages,
            model=resolve_model(phase=debate.phase),
            temperature=0.7,
            debate_id=debate.id,
            operation="assist",
        )
        return _parse_assist(raw, side, sources)
    except (DeepSeekError, ValueError, KeyError):
        return _fallback_assist(side, sources)


async def generate_assist_stream_events(debate: DebateState, side: str, draft: str) -> AsyncIterator[dict]:
    messages, sources = _assist_messages(debate, side, draft)
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
            result = _parse_assist(raw, side, sources)
        except Exception:
            result = _fallback_assist(side, sources)
        yield {"type": "done", "data": result}
    except DeepSeekError as exc:
        yield {"type": "error", "message": str(exc)}
        yield {"type": "done", "data": _fallback_assist(side, sources)}
