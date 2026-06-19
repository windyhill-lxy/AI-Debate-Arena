from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Literal

from app.models import Source
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream
from app.services.rag import retrieve_sources


def _topic_keyword(topic: str) -> str:
    topic = re.sub(r"\s+", "", topic or "")
    if "是否" in topic:
        return topic.split("是否", 1)[0] or topic
    return topic[:18] or "本辩题"


def _sentence_count(text: str) -> int:
    return len([p for p in re.split(r"[。！？.!?]\s*", text or "") if p.strip()])


def _has_three_arguments(text: str) -> bool:
    markers = ["第一", "第二", "第三"]
    if all(marker in text for marker in markers):
        return True
    numbered = re.findall(r"(?:^|\n)\s*(?:[1-3][.、]|[一二三][、.])", text)
    return len(numbered) >= 3


def _citation_risk(text: str, sources: list[Source]) -> str:
    risky_terms = ("研究表明", "数据显示", "%", "法律规定", "论文指出", "报告显示")
    if any(term in text for term in risky_terms) and not sources:
        return "high"
    if re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%|\d+\s*(万|亿|人|项|次)", text) and not sources:
        return "medium"
    return "low"


def analyze_opening_draft(topic: str, side: Literal["affirmative", "negative"], draft: str) -> dict:
    text = (draft or "").strip()
    if not text:
        raise ValueError("立论内容不能为空")

    sources = retrieve_sources(topic, text, debate_id=None)
    has_definition = any(word in text for word in ("定义", "标准", "核心争议", "判断标准", "何谓"))
    has_three = _has_three_arguments(text)
    has_closing = any(word in text[-120:] for word in ("综上", "因此", "所以我方", "由此可见"))
    sentence_count = _sentence_count(text)
    risk = _citation_risk(text, sources)

    score = 38
    score += 12 if has_definition else 0
    score += 18 if has_three else 0
    score += 9 if has_closing else 0
    score += 8 if 10 <= sentence_count <= 36 else 3
    score += min(len(sources), 3) * 4
    if len(text) < 700:
        score -= 8
    if risk == "high":
        score -= 12
    elif risk == "medium":
        score -= 6
    score = max(0, min(94, score))

    advice: list[str] = []
    if not has_definition:
        advice.append("开头补一句辩题定义和判断标准，让裁判知道你用什么标准赢。")
    if not has_three:
        advice.append("把主体改成三个清晰分论点，每个分论点配一个可验证论据。")
    if risk != "low":
        advice.append("涉及数据、研究、法规时补充来源；没有来源就改成经验判断或待查表述。")
    if not has_closing:
        advice.append("结尾用 2-3 句回扣标准，明确为什么本方更能实现辩题价值。")
    if score < 88 and has_definition and has_three and has_closing:
        advice.append("目前只是结构完整，还要补充更具体的案例来源、反方预判和标准比较，才能达到高水平一辩立论。")
    if not advice:
        advice.append("整体结构可用，下一步重点压缩重复表达并增强对反方预判。")

    side_label = "正方" if side == "affirmative" else "反方"
    revision = (
        f"{side_label}一辩可按「定义标准 - 三个分论点 - 价值收束」重写："
        f"先界定辩题关键词，再把最强论据放在第一点，最后预判对方可能攻击并提前回应。"
    )

    return {
        "topic": topic,
        "side": side,
        "score": score,
        "structure": {
            "has_definition": has_definition,
            "has_three_arguments": has_three,
            "has_closing": has_closing,
            "sentence_count": sentence_count,
        },
        "rag_checks": {
            "sources_found": len(sources),
            "hallucination_risk": risk,
            "sources": [s.model_dump() for s in sources[:4]],
        },
        "revision_advice": advice,
        "suggested_revision_strategy": revision,
    }


def _opening_standard_met(analysis: dict) -> bool:
    structure = analysis.get("structure", {})
    rag_checks = analysis.get("rag_checks", {})
    return (
        analysis.get("score", 0) >= 90
        and structure.get("has_definition") is True
        and structure.get("has_three_arguments") is True
        and structure.get("has_closing") is True
        and rag_checks.get("hallucination_risk") != "high"
    )


def _review_says_not_ready(review: str) -> bool:
    return bool(re.search(r"尚未达到|未达到|不达标|还不能|不能按满分|需要继续|下一轮必须", review or ""))


def _clean_speech_text(text: str) -> str:
    text = re.sub(r"[*#>`_~]+", "", text or "")
    text = text.replace("——", "，").replace("--", "，").replace("—", "，")
    text = re.sub(r"\n\s*(?:[-*]|\d+[.、])\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fallback_opening(topic: str, side: Literal["affirmative", "negative"], advice: list[str] | None = None) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    key = _topic_keyword(topic)
    if side == "affirmative":
        points = [
            f"第一，{key}能够降低学习和训练中的反馈成本，让学生更快知道问题在哪里，也更容易把一次练习转化为下一次改进。",
            f"第二，{key}能够扩展材料来源和表达角度，使学生在比较不同观点时形成更完整的判断，而不是只停留在单一经验里。",
            f"第三，{key}能够帮助学生复盘思路，发现论证跳步、概念混用和证据不足，从而提升综合学习能力。",
        ]
        value = "因此，我方认为只要把 AI 放在辅助位置，并保留教师指导和学生主动思考，它提升的是学习过程中的反馈、材料和复盘能力。"
    else:
        points = [
            f"第一，{key}如果被过度使用，会让学生把检索、判断和表达外包出去，长期看会削弱独立建构知识的能力。",
            f"第二，{key}提供的答案并不天然可靠，学生若缺少核验能力，容易把不准确材料当成结论使用。",
            f"第三，{key}无法替代真实课堂中的交流、追问和情境判断，而这些才是综合学习能力的重要来源。",
        ]
        value = "因此，我方认为 AI 可以作为工具存在，但它本身并不必然提升综合学习能力，关键能力仍来自主动思考、真实互动和持续训练。"
    advice_note = ""
    if advice:
        advice_note = "根据前轮建议，本稿特别补强定义、三条论证链和结尾回扣标准。"
    return "\n".join(
        [
            f"主席、评委、对方辩友，大家好。我方作为{side_label}，认为本题的核心不是讨论工具是否新奇，而是判断它能否稳定促进学生的理解、迁移和表达。这里的综合学习能力，指的是获取信息、辨析信息、形成观点并把观点清楚表达出来的能力。{advice_note}",
            *points,
            value,
            f"综上，我方的判断标准是，哪一方更能说明学生能力是否被真实训练、稳定迁移并长期保留，哪一方就更符合本辩题的要求。",
        ]
    )


async def _generate_opening_with_ai(
    topic: str,
    side: Literal["affirmative", "negative"],
    advice: list[str],
    previous_drafts: list[str],
) -> str:
    messages = _opening_generation_messages(topic, side, advice, previous_drafts)
    try:
        draft = await chat_completion(messages, temperature=0.55, max_tokens=1800, operation="opening_training_auto_improve")
        return _clean_speech_text(draft)
    except (DeepSeekError, Exception):
        return _fallback_opening(topic, side, advice)


def _opening_generation_messages(
    topic: str,
    side: Literal["affirmative", "negative"],
    advice: list[str],
    previous_drafts: list[str],
) -> list[dict[str, str]]:
    side_label = "正方" if side == "affirmative" else "反方"
    advice_text = "\n".join(advice[-10:]) or "先生成完整一辩立论。"
    previous_text = "\n\n".join(previous_drafts[-2:]) or "无"
    return [
        {
            "role": "system",
            "content": (
                "你是一名资深中文辩论一辩教练。只输出可朗读的完整一辩立论正文。"
                "不要使用破折号、星号粗体、代码块或复杂分点。语言要自然，适合现场朗读。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{topic}\n持方：{side_label}\n"
                f"此前修改建议：\n{advice_text}\n"
                f"此前稿件：\n{previous_text}\n"
                "请生成一篇包含定义、判断标准、三个论点和结尾收束的一辩立论。"
            ),
        },
    ]


async def _stream_opening_with_ai(
    topic: str,
    side: Literal["affirmative", "negative"],
    advice: list[str],
    previous_drafts: list[str],
) -> AsyncIterator[str]:
    messages = _opening_generation_messages(topic, side, advice, previous_drafts)
    try:
        async for chunk in chat_completion_stream(
            messages,
            temperature=0.55,
            max_tokens=1800,
            operation="opening_training_auto_improve_stream",
        ):
            if chunk:
                for index in range(0, len(chunk), 36):
                    yield chunk[index:index + 36]
                    await asyncio.sleep(0)
    except (DeepSeekError, Exception):
        fallback = _fallback_opening(topic, side, advice)
        for index in range(0, len(fallback), 48):
            yield fallback[index:index + 48]


def _analysis_summary(analysis: dict) -> str:
    risk = analysis.get("rag_checks", {}).get("hallucination_risk", "unknown")
    structure = analysis.get("structure", {})
    advice_items = analysis.get("revision_advice", [])
    advice = " ".join(advice_items)
    sources_found = analysis.get("rag_checks", {}).get("sources_found", 0)
    return (
        f"本轮评分 {analysis.get('score', 0)} 分。事实风险为 {risk}，RAG 找到 {sources_found} 条可参考资料。"
        f"结构检查方面，定义和标准{'已经出现' if structure.get('has_definition') else '仍需补充'}，"
        f"三个分论点{'基本完整' if structure.get('has_three_arguments') else '还不够清楚'}，"
        f"结尾收束{'已经出现' if structure.get('has_closing') else '需要补上'}。"
        f"修改重点是：{advice}"
    )


def _detailed_review_fallback(topic: str, side: Literal["affirmative", "negative"], draft: str, analysis: dict) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    advice = " ".join(analysis.get("revision_advice", []))
    return (
        f"本轮审核：{side_label}一辩稿目前得到 {analysis.get('score', 0)} 分，还不能按满分稿处理。"
        f"从一辩标准看，它必须同时完成定义、判断标准、三条主论证、证据支撑、反方预判和价值收束。"
        f"现在最需要检查的是，定义是否能直接服务于辩题「{topic}」，标准是否能让裁判据此比较正反双方，"
        f"每个论点是否都有具体事实或案例支撑，而不是只停留在抽象判断。"
        f"RAG 校验显示事实风险为 {analysis.get('rag_checks', {}).get('hallucination_risk', 'unknown')}，"
        f"可参考资料数量为 {analysis.get('rag_checks', {}).get('sources_found', 0)} 条。"
        f"下一版请按这个顺序修改：先把核心概念界定清楚，再把第一论点写成最强战场，"
        f"然后给第二、第三论点各补一个可核验案例，最后用两三句话说明为什么本方标准更能赢下比较。"
        f"具体建议：{advice}"
    )


async def _review_opening_with_ai(
    topic: str,
    side: Literal["affirmative", "negative"],
    draft: str,
    analysis: dict,
) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    prompt = (
        f"辩题：{topic}\n持方：{side_label}\n"
        f"机器结构评分：{analysis.get('score', 0)}\n"
        f"结构检查：{analysis.get('structure', {})}\n"
        f"RAG 检查：{analysis.get('rag_checks', {})}\n"
        f"初步建议：{analysis.get('revision_advice', [])}\n"
        f"待审核立论：\n{draft}\n\n"
        "请以严格辩论裁判兼一辩教练身份，输出详细审核意见。"
        "必须包含：是否达标、结构问题、论据问题、事实核验风险、对方可能攻击点、下一版具体改法。"
        "语言要自然，适合前端直接朗读，不要使用破折号、星号粗体或代码块。"
    )
    try:
        review = await chat_completion(
            [
                {
                    "role": "system",
                    "content": "你是中文辩论赛一辩教练和严格裁判。只输出详细审核意见，不要替辩手直接重写全文。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
            max_tokens=1400,
            operation="opening_training_review",
        )
        cleaned = _clean_speech_text(review)
        if len(cleaned) >= 180 and any(term in cleaned for term in ("结构", "论据", "下一版", "修改")):
            return cleaned
    except (DeepSeekError, Exception):
        pass
    return _detailed_review_fallback(topic, side, draft, analysis)


async def auto_improve_opening_draft(
    topic: str,
    side: Literal["affirmative", "negative"],
    max_rounds: int = 6,
) -> dict:
    if not (topic or "").strip():
        raise ValueError("辩题不能为空")
    max_rounds = max(1, min(12, int(max_rounds or 6)))
    rounds: list[dict] = []
    conversation: list[dict] = []
    advice_memory: list[str] = []
    previous_drafts: list[str] = []
    final_draft = ""
    final_analysis: dict | None = None
    passed = False

    writer_avatar = "/src/assets/agents/agent-silver.png" if side == "affirmative" else "/src/assets/agents/agent-orange.png"
    reviewer_avatar = "/src/assets/agents/agent-purple.png"
    writer_name = "AI一辩"
    reviewer_name = "AI教练"

    for round_index in range(1, max_rounds + 1):
        draft = await _generate_opening_with_ai(topic, side, advice_memory, previous_drafts)
        analysis = analyze_opening_draft(topic, side, draft)
        review_text = await _review_opening_with_ai(topic, side, draft, analysis)
        current_passed = _opening_standard_met(analysis) and not _review_says_not_ready(review_text)
        final_draft = draft
        final_analysis = analysis
        passed = current_passed
        round_record = {
            "round": round_index,
            "draft": draft,
            "analysis": analysis,
            "passed": current_passed,
            "advice": analysis["revision_advice"],
        }
        rounds.append(round_record)
        conversation.append(
            {
                "id": f"draft-{round_index}",
                "role": "writer",
                "speaker_name": writer_name,
                "avatar": writer_avatar,
                "kind": "draft",
                "round": round_index,
                "content": draft,
            }
        )
        conversation.append(
            {
                "id": f"review-{round_index}",
                "role": "reviewer",
                "speaker_name": reviewer_name,
                "avatar": reviewer_avatar,
                "kind": "analysis",
                "round": round_index,
                "content": review_text,
            }
        )
        if current_passed and (round_index >= 2 or max_rounds == 1):
            break
        previous_drafts.append(draft)
        advice_memory.extend(analysis["revision_advice"])

    return {
        "topic": topic,
        "side": side,
        "max_rounds": max_rounds,
        "passed": passed,
        "final_draft": final_draft,
        "final_score": final_analysis["score"] if final_analysis else 0,
        "rounds": rounds,
        "conversation": conversation,
    }


async def auto_improve_opening_draft_events(
    topic: str,
    side: Literal["affirmative", "negative"],
    max_rounds: int = 6,
) -> AsyncIterator[dict]:
    if not (topic or "").strip():
        yield {"type": "error", "message": "辩题不能为空"}
        return
    max_rounds = max(1, min(12, int(max_rounds or 6)))
    advice_memory: list[str] = []
    previous_drafts: list[str] = []
    rounds: list[dict] = []
    conversation: list[dict] = []
    passed = False
    final_draft = ""
    final_analysis: dict | None = None
    writer_avatar = "/src/assets/agents/agent-silver.png" if side == "affirmative" else "/src/assets/agents/agent-orange.png"
    reviewer_avatar = "/src/assets/agents/agent-purple.png"

    for round_index in range(1, max_rounds + 1):
        draft_id = f"draft-{round_index}"
        full_draft = ""
        draft_event = {
            "id": draft_id,
            "role": "writer",
            "speaker_name": "AI一辩",
            "avatar": writer_avatar,
            "kind": "draft",
            "round": round_index,
            "content": "",
        }
        conversation.append(draft_event)
        yield {"type": "draft_start", "message": draft_event}
        async for chunk in _stream_opening_with_ai(topic, side, advice_memory, previous_drafts):
            full_draft += chunk
            cleaned = _clean_speech_text(full_draft)
            draft_event = {**draft_event, "content": cleaned}
            conversation[-1] = draft_event
            yield {"type": "draft_delta", "message": draft_event, "text": chunk, "full_text": cleaned}
        draft = _clean_speech_text(full_draft)
        conversation[-1] = {**conversation[-1], "content": draft}
        draft_event = {
            "id": draft_id,
            "role": "writer",
            "speaker_name": "AI一辩",
            "avatar": writer_avatar,
            "kind": "draft",
            "round": round_index,
            "content": draft,
        }
        yield {"type": "draft", "message": draft_event}

        analysis = analyze_opening_draft(topic, side, draft)
        review_text = await _review_opening_with_ai(topic, side, draft, analysis)
        current_passed = _opening_standard_met(analysis) and not _review_says_not_ready(review_text)
        review_event = {
            "id": f"review-{round_index}",
            "role": "reviewer",
            "speaker_name": "AI裁判",
            "avatar": reviewer_avatar,
            "kind": "analysis",
            "round": round_index,
            "content": review_text,
        }
        conversation.append(review_event)
        yield {"type": "review", "message": review_event, "analysis": analysis, "passed": current_passed}

        rounds.append(
            {
                "round": round_index,
                "draft": draft,
                "analysis": analysis,
                "passed": current_passed,
                "advice": analysis["revision_advice"],
            }
        )
        final_draft = draft
        final_analysis = analysis
        passed = current_passed
        if current_passed and (round_index >= 2 or max_rounds == 1):
            break
        previous_drafts.append(draft)
        advice_memory.extend(analysis["revision_advice"])

    yield {
        "type": "done",
        "data": {
            "topic": topic,
            "side": side,
            "max_rounds": max_rounds,
            "passed": passed,
            "final_draft": final_draft,
            "final_score": final_analysis["score"] if final_analysis else 0,
            "rounds": rounds,
            "conversation": conversation,
        },
    }


async def polish_opening_draft(
    topic: str,
    side: Literal["affirmative", "negative"],
    draft: str,
    advice: list[str] | None = None,
) -> dict:
    text = (draft or "").strip()
    if not text:
        raise ValueError("立论内容不能为空")
    analysis = analyze_opening_draft(topic, side, text)
    advice_text = "\n".join((advice or []) + analysis.get("revision_advice", []))
    side_label = "正方" if side == "affirmative" else "反方"
    try:
        polished = await chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "你是中文辩论一辩教练。请在保留原立场和核心意思的基础上润色成正式一辩立论。"
                        "不要使用破折号、星号粗体、代码块。语言要流畅，适合现场朗读。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"辩题：{topic}\n持方：{side_label}\n"
                        f"修改建议：\n{advice_text}\n"
                        f"原稿：\n{text}\n\n"
                        "请输出润色后的完整一辩立论稿，包含定义、判断标准、三个论点、论据补强和结尾收束。"
                    ),
                },
            ],
            temperature=0.45,
            max_tokens=1800,
            operation="opening_training_polish",
        )
        polished = _clean_speech_text(polished)
    except (DeepSeekError, Exception):
        polished = _fallback_opening(topic, side, analysis.get("revision_advice", []))
    return {
        "topic": topic,
        "side": side,
        "analysis": analysis,
        "polished_draft": polished,
    }
