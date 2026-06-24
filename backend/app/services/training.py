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


def _opening_dimension_scores(
    *,
    has_definition: bool,
    has_three: bool,
    has_closing: bool,
    sentence_count: int,
    sources: list[Source],
    risk: str,
    text: str,
) -> list[dict]:
    argument_markers = sum(1 for marker in ("第一", "第二", "第三") if marker in text)
    definition_score = 18 if has_definition else 7
    structure_score = 24 if has_three else 10 + argument_markers * 4
    evidence_score = 8 + min(len(sources), 3) * 4
    if re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%|\d+\s*(万|亿|人|项|次)", text):
        evidence_score += 3
    evidence_score = min(20, evidence_score)
    reliability_score = {"low": 15, "medium": 9, "high": 4}.get(risk, 8)
    expression_score = 10
    if has_closing:
        expression_score += 6
    if 10 <= sentence_count <= 36:
        expression_score += 3
    if len(text) >= 700:
        expression_score += 1
    expression_score = min(20, expression_score)
    return [
        {"key": "definition", "label": "定义与标准", "score": definition_score, "max_score": 20},
        {"key": "structure", "label": "论证结构", "score": min(25, structure_score), "max_score": 25},
        {"key": "evidence", "label": "论据支撑", "score": evidence_score, "max_score": 20},
        {"key": "reliability", "label": "事实可靠", "score": reliability_score, "max_score": 15},
        {"key": "expression", "label": "表达收束", "score": expression_score, "max_score": 20},
    ]


def _opening_evaluation(score: int, risk: str, has_three: bool) -> str:
    if score >= 90 and risk != "high":
        return "已经接近正式比赛可用稿，下一步主要压缩重复表达并增强临场气势。"
    if score >= 78:
        return "整体框架已经成型，但论据密度和反方预判还需要继续补强。"
    if has_three:
        return "三段论证雏形已经出现，但定义、证据或结尾比较还不足以支撑高分。"
    return "目前更像观点草稿，还需要先搭起定义、判断标准和三条清晰论证链。"


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

    dimensions = _opening_dimension_scores(
        has_definition=has_definition,
        has_three=has_three,
        has_closing=has_closing,
        sentence_count=sentence_count,
        sources=sources,
        risk=risk,
        text=text,
    )
    score = max(0, min(98, sum(item["score"] for item in dimensions)))

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
        "score_summary": {
            "overall": score,
            "label": "综合分",
            "evaluation": _opening_evaluation(score, risk, has_three),
            "improvement_suggestions": advice,
        },
        "dimensions": dimensions,
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
            f"第一，{key}能够降低学习和训练中的反馈成本。传统学习中，学生常常要等到作业批改、课堂讲评或考试之后才知道自己错在哪里，反馈延迟会让错误方法被反复使用。AI 辅助学习的价值正在于把反馈前移，让学生在练习当场看到概念漏洞、步骤缺口和表达问题，再把一次错误转化为下一轮修改。只要教师仍然保留评价权，AI 提供的不是替代思考的答案，而是更快出现的镜子。",
            f"第二，{key}能够扩展材料来源和表达角度。综合学习能力不是背出单一结论，而是在不同材料之间比较、筛选、组织和表达。AI 可以把教材、案例、类比和反例同时摆到学生面前，帮助学生看到同一问题的不同解释路径。学生如果在教师要求下说明为什么选用某条材料、为什么放弃另一条材料，实际训练的正是信息辨析和观点建构能力。",
            f"第三，{key}能够帮助学生复盘思路，发现论证跳步、概念混用和证据不足。很多学生不是没有观点，而是不知道自己的观点哪里断裂。AI 对提纲、作文、解题过程和口头表达进行追问式反馈，可以让学生意识到“我会说”与“我说得成立”之间的差距。综合学习能力最终要落在迁移和表达上，复盘恰恰能把零散知识变成可迁移的方法。",
        ]
        value = "当然，我方并不主张把 AI 当成万能老师，更不主张让学生复制答案。正因为存在依赖风险，学校才应把 AI 纳入明确规则：先由学生独立作答，再用 AI 检查漏洞，最后由学生解释修改理由。这样，工具被限制在辅助位置，学生仍然承担理解、判断和表达的责任。"
    else:
        points = [
            f"第一，{key}如果被过度使用，会让学生把检索、判断和表达外包出去。综合学习能力的形成依赖困难中的主动加工：学生要自己读材料、比较信息、尝试表达，再从错误中修正。AI 如果直接给出答案、提纲和漂亮措辞，学生最容易训练出的不是能力，而是调用工具的熟练度。短期看效率提高，长期看独立建构知识的机会被压缩。",
            f"第二，{key}提供的答案并不天然可靠。青少年还处在判断标准建立阶段，如果没有足够的事实核验能力，很容易把看似流畅的解释当成正确结论。学习能力的关键不是得到一个像样答案，而是知道答案为什么成立、边界在哪里、证据是否足够。AI 的不确定性会把核验负担提前压到学生身上，而这恰恰是许多学生尚未具备的能力。",
            f"第三，{key}无法替代真实课堂中的交流、追问和情境判断。综合学习能力包括倾听、提问、协作、表达和价值判断，这些能力是在真实互动中被磨出来的。AI 可以模拟反馈，却不能承担教师观察学生状态、同伴互相质疑、课堂即时调整这些复杂过程。把提升能力寄托在工具上，容易忽视学习共同体本身的训练价值。",
        ]
        value = "我方也承认，AI 在查资料、改错别字、提供练习题方面可以作为辅助工具存在。但“可以辅助”不等于“会提升综合学习能力”。如果使用规则、教师监督和学生自律稍有不足，它更可能让学生绕过困难，而不是穿过困难。"
    advice_note = ""
    if advice:
        advice_note = "根据前轮建议，本稿特别补强定义、三条论证链和结尾回扣标准。"
    return "\n".join(
        [
            f"主席、评委、对方辩友，大家好。我方作为{side_label}，认为本题的核心不是讨论工具是否新奇，而是判断它能否稳定促进学生的理解、迁移和表达。这里的综合学习能力，指的是获取信息、辨析信息、形成观点并把观点清楚表达出来的能力。{advice_note}",
            *points,
            value,
            f"综上，我方的判断标准是，哪一方更能说明学生能力是否被真实训练、稳定迁移并长期保留，哪一方就更符合本辩题的要求。按照这个标准，{side_label}更能解释学习能力的来源、条件和长期结果，因此我方立场成立。",
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
        draft = await chat_completion(messages, temperature=0.55, max_tokens=3600, operation="opening_training_auto_improve")
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
                "必须输出 Markdown 文本，可使用二级标题和自然段，但不要使用代码块。"
                "不要使用破折号、星号粗体或复杂分点。语言要自然，适合现场朗读。"
                "目标长度为 800 到 1000 个汉字，不能只写提纲，不能在三个论点和结尾收束完成前结束。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"辩题：{topic}\n持方：{side_label}\n"
                f"此前修改建议：\n{advice_text}\n"
                f"此前稿件：\n{previous_text}\n"
                "请生成一篇完整一辩立论，必须包含定义、判断标准、三个有证据意识的论点、对反方可能攻击的预判和结尾收束。"
                "全文要像正式比赛发言，使用 Markdown 自然段呈现，不要列清单，不要用破折号，不要用星号。"
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
            max_tokens=3600,
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


def _judge_score_block(analysis: dict) -> str:
    summary = analysis.get("score_summary", {})
    dimensions = analysis.get("dimensions", [])
    advice = summary.get("improvement_suggestions") or analysis.get("revision_advice", [])
    dimension_text = "；".join(
        f"{item.get('label')} {item.get('score')}/{item.get('max_score')}" for item in dimensions
    )
    advice_text = "；".join(advice[:4])
    return (
        f"综合分数：{summary.get('overall', analysis.get('score', 0))} 分。\n"
        f"多维度评分：{dimension_text}。\n"
        f"评价：{summary.get('evaluation', '暂无评价')}。\n"
        f"改进建议：{advice_text}。"
    )


def _review_generation_messages(
    topic: str,
    side: Literal["affirmative", "negative"],
    draft: str,
    analysis: dict,
) -> list[dict[str, str]]:
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
        "不要另造 KB-A 等资料编号；如果提到资料引用，只使用系统已有编号。"
        "审核意见不少于五百个汉字，要具体到可修改的句子和论证链，不要只给一两句结论。"
        "语言要自然，适合前端直接朗读，不要使用破折号、星号粗体或代码块。"
    )
    return [
        {
            "role": "system",
            "content": "你是中文辩论赛一辩教练和严格裁判。只输出详细审核意见，不要替辩手直接重写全文。",
        },
        {"role": "user", "content": prompt},
    ]


def _detailed_review_fallback(topic: str, side: Literal["affirmative", "negative"], draft: str, analysis: dict) -> str:
    side_label = "正方" if side == "affirmative" else "反方"
    advice = " ".join(analysis.get("revision_advice", []))
    return (
        f"{_judge_score_block(analysis)}\n\n"
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
    try:
        review = await chat_completion(
            _review_generation_messages(topic, side, draft, analysis),
            temperature=0.35,
            max_tokens=2600,
            operation="opening_training_review",
        )
        cleaned = _clean_speech_text(review)
        if len(cleaned) >= 180 and any(term in cleaned for term in ("结构", "论据", "下一版", "修改")):
            return f"{_judge_score_block(analysis)}\n\n{cleaned}"
    except (DeepSeekError, Exception):
        pass
    return _detailed_review_fallback(topic, side, draft, analysis)


async def _stream_review_with_ai(
    topic: str,
    side: Literal["affirmative", "negative"],
    draft: str,
    analysis: dict,
) -> AsyncIterator[str]:
    full_text = ""
    score_block = f"{_judge_score_block(analysis)}\n\n"
    yield score_block
    try:
        async for chunk in chat_completion_stream(
            _review_generation_messages(topic, side, draft, analysis),
            temperature=0.35,
            max_tokens=2600,
            operation="opening_training_review_stream",
        ):
            if not chunk:
                continue
            for index in range(0, len(chunk), 36):
                piece = chunk[index:index + 36]
                full_text += piece
                yield piece
                await asyncio.sleep(0)
        cleaned = _clean_speech_text(full_text)
        if len(cleaned) >= 180 and any(term in cleaned for term in ("结构", "论据", "下一版", "修改")):
            return
    except (DeepSeekError, Exception):
        pass
    fallback = _detailed_review_fallback(topic, side, draft, analysis)
    if _clean_speech_text(full_text) == _clean_speech_text(fallback):
        return
    for index in range(0, len(fallback), 48):
        yield fallback[index:index + 48]
        await asyncio.sleep(0)


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
        review_text = ""
        review_id = f"review-{round_index}"
        review_event = {
            "id": review_id,
            "role": "reviewer",
            "speaker_name": "AI裁判",
            "avatar": reviewer_avatar,
            "kind": "analysis",
            "round": round_index,
            "content": "",
        }
        conversation.append(review_event)
        yield {"type": "review_start", "message": review_event, "analysis": analysis}
        async for chunk in _stream_review_with_ai(topic, side, draft, analysis):
            review_text = _clean_speech_text(review_text + chunk)
            review_event = {**review_event, "content": review_text}
            conversation[-1] = review_event
            yield {"type": "review_delta", "message": review_event, "text": chunk, "full_text": review_text}
        current_passed = _opening_standard_met(analysis) and not _review_says_not_ready(review_text)
        review_event = {
            "id": review_id,
            "role": "reviewer",
            "speaker_name": "AI裁判",
            "avatar": reviewer_avatar,
            "kind": "analysis",
            "round": round_index,
            "content": review_text,
        }
        conversation[-1] = review_event
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
            max_tokens=3200,
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
