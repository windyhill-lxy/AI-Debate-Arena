import asyncio
import re
from collections.abc import Awaitable, Callable
from app.core.time_utils import utc_now
from app.services.citations import has_unverified_citations, sanitize_citations
from typing import Any
from uuid import uuid4

try:
    from langgraph.graph import END, StateGraph
except Exception:
    END = "__end__"
    StateGraph = None

from app.models import DebateMessage, DebateState, Source, build_schedule_status
from app.services.ai_context_manager import build_ai_debater_context, format_argument_bank
from app.services.argument_bank import (
    add_message_arguments_to_bank_with_ai_titles,
    add_sources_to_argument_bank,
    argument_count_for_side,
    argument_ids_for_side,
    opening_argument_bank_ready,
    referenced_argument_ids,
)
from app.services.debate_mode import peek_next_speaker_id
from app.services.debate_schedule import advance_schedule, segment_prompt_hint
from app.services.llm import (
    DeepSeekError,
    chat_completion,
    chat_completion_stream,
    resolve_model,
    strip_model_reasoning,
)
from app.services.message_visibility import latest_any_visible_message
from app.services.judge_report import generate_final_report
from app.services.opening_evidence import current_segment_id, ensure_opening_argument_bank, needs_opening_evidence
from app.services.rag import retrieve_sources
from app.services.team_discussion import (
    TeamDiscussionContext,
    argument_ids_for_prompt,
    build_team_discussion_user_content,
    generate_team_discussion_draft,
    team_discussion_speakers,
)

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
PUBLIC_DEBATE_PHASES = {
    "opening_statement",
    "rebuttal",
    "cross_examination",
    "segment_summary",
    "free_debate",
    "closing",
}
RAG_SEGMENT_IDS = {
    "aff_opening_rag",
    "neg_opening_rag",
    "neg_rebuttal_rag",
    "aff_rebuttal_rag",
    "aff_summary_fact",
    "neg_summary_fact",
    "free_predict_rag",
    "free_case_rag",
    "free_realtime_rag",
    "closing_knowledge_rag",
    "closing_neg_rag",
    "closing_aff_rag",
    "judge_criteria_rag",
}


def _is_public_debate_phase(phase: str) -> bool:
    return phase in PUBLIC_DEBATE_PHASES


def _is_internal_team_phase(phase: str) -> bool:
    return phase in {"opening_prep", "free_prep", "closing_prep"}


def _is_task_assign_segment(segment_label: str) -> bool:
    return "任务分配" in (segment_label or "")


def _is_team_discussion_segment(debate: DebateState) -> bool:
    return _is_internal_team_phase(debate.phase) and "队内讨论" in (debate.segment_label or "")


def _has_prior_judge_pre_match(debate: DebateState) -> bool:
    return any(m.side == "judge" and m.phase == "pre_match" for m in debate.messages)


def _framework_looks_incomplete(text: str) -> bool:
    """Announced multi-part argument structure but missing later parts."""
    if re.search(r"分两层|框架分两层|论证框架分两层", text) and not re.search(r"第二[，,、]", text):
        return True
    if re.search(r"三层递进|分三层|论证框架分三层", text) and not re.search(r"第三[，,、]", text):
        return True
    if re.search(r"三个维度", text) and re.search(r"论证框架分三层|分三层递进", text):
        if not re.search(r"第三[，,、]", text):
            return True
    return False


def _looks_incomplete(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return True
    if _framework_looks_incomplete(stripped):
        return True
    if stripped[-1] in "。！？.!?）)」』”’":
        return False
    dangling_suffixes = (
        "一旦",
        "如果",
        "因为",
        "所以",
        "但是",
        "同时",
        "并且",
        "例如",
        "包括",
        "第一",
        "第二",
        "第三",
        "：",
        ":",
        "，",
        ",",
        "、",
        "；",
        ";",
    )
    return any(stripped.endswith(suffix) for suffix in dangling_suffixes) or len(stripped) < 24


def _has_substantive_completion(text: str, debate: DebateState) -> bool:
    stripped = re.sub(r"\s+", "", strip_model_reasoning(text or ""))
    if not stripped:
        return False
    if _looks_incomplete(stripped):
        return False
    min_chars = {
        "cross_examination": 48,
        "rebuttal": 70,
        "segment_summary": 70,
        "opening_statement": 820,
        "closing": 220,
    }.get(debate.phase, 24)
    if len(stripped) < min_chars:
        return False
    if debate.phase == "cross_examination":
        if _cross_examination_mode(debate.segment_label or "") == "question":
            return stripped.count("请问") >= 1 and len(re.findall(r"[?？]", stripped)) >= 1
        return bool(re.search(r"第一问|第二问|回应|因此|所以", stripped))
    return True


def _completion_target_chars(debate: DebateState) -> int:
    return {
        "opening_statement": 900,
        "closing": 650,
    }.get(debate.phase, 0)


def _max_tokens_for_phase(phase: str) -> int:
    return {
        "opening_statement": 3500,
        "closing": 3200,
        "cross_examination": 1200,
        "segment_summary": 1400,
        "rebuttal": 1600,
        "free_debate": 800,
    }.get(phase, 1400)


def _max_sentences_for_phase(phase: str, segment_seconds: int = 60) -> int | None:
    if phase == "free_debate":
        return 1
    if phase == "opening_statement":
        return max(22, min(36, segment_seconds // 6))
    if phase == "closing":
        return max(20, min(32, segment_seconds // 7))
    if phase == "rebuttal":
        return 5
    if phase == "cross_examination":
        return 5
    if phase == "segment_summary":
        return 6
    return None


def _limit_sentences(text: str, max_sentences: int) -> str:
    parts = [p for p in re.split(r"(?<=[。！？.!?])\s*", text.strip()) if p]
    if len(parts) <= max_sentences:
        return text.strip()
    trimmed = "".join(parts[:max_sentences]).strip()
    if trimmed and trimmed[-1] not in "。！？.!?":
        trimmed += "。"
    return trimmed


def _apply_phase_speech_limits(content: str, debate: DebateState) -> str:
    """Only hard-trim runaway outputs; never shorten normal-length speeches after streaming."""
    text = (content or "").strip()
    if not text:
        return text
    if debate.phase == "free_debate":
        return _limit_sentences(text, 1)
    char_cap = {
        "opening_statement": 4500,
        "closing": 3800,
        "cross_examination": 1600,
        "segment_summary": 1800,
        "rebuttal": 1600,
    }.get(debate.phase)
    if not char_cap or len(text) <= char_cap:
        return text
    parts = [p for p in re.split(r"(?<=[。！？.!?])\s*", text) if p]
    out = ""
    for part in parts:
        if len(out) + len(part) > char_cap:
            break
        out += part
    return out.strip() or text[:char_cap]


def _cross_examination_mode(segment_label: str) -> str:
    label = (segment_label or "").strip()
    if any(token in label for token in ("回应盘问", "回应质询", "回答", "作答")):
        return "respond"
    if any(token in label for token in ("盘问", "质询", "提问")) or re.search(r"问[正反]方[一二三四]辩", label):
        return "question"
    return "respond"


def _argument_ids_for_prompt(debate: DebateState, side: str) -> str:
    return argument_ids_for_prompt(debate, side)


def _sanitize_content_preserving_argument_ids(content: str, sources: list[Source]) -> str:
    placeholders: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = f"__ARG_ID_{len(placeholders)}__"
        placeholders[key] = f"[{match.group(1).upper()}]"
        return key

    protected = re.sub(r"\[\s*((?:AFF|NEG)-\d+)\s*\]", protect, content or "", flags=re.IGNORECASE)
    cleaned = sanitize_citations(protected, sources)
    for key, value in placeholders.items():
        cleaned = cleaned.replace(key, value)
    return cleaned


def _has_unverified_citations_preserving_argument_ids(content: str, sources: list[Source]) -> bool:
    without_argument_ids = re.sub(r"\[\s*(?:AFF|NEG)-\d+\s*\]", "", content or "", flags=re.IGNORECASE)
    return has_unverified_citations(without_argument_ids, sources)


class DebateGraph:
    """LangGraph agentic loop backed by DeepSeek."""

    def __init__(self) -> None:
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        if StateGraph is None:
            return None

        graph = StateGraph(dict)
        graph.add_node("rag_retrieve", self._rag_retrieve)
        graph.add_node("opening_evidence_retrieve", self._opening_evidence_retrieve)
        graph.add_node("strategy_plan", self._strategy_plan)
        graph.add_node("stance_decision", self._stance_decision)
        graph.add_node("reflection", self._reflection)
        graph.add_node("speech_generate", self._speech_generate_streaming)
        graph.add_node("fact_check", self._fact_check)
        graph.add_node("publish_message", self._publish_message)
        graph.add_node("judge_score", self._judge_score)
        graph.add_node("turn_router", self._turn_router)

        graph.set_entry_point("rag_retrieve")
        graph.add_edge("rag_retrieve", "opening_evidence_retrieve")
        graph.add_edge("opening_evidence_retrieve", "strategy_plan")
        graph.add_edge("strategy_plan", "stance_decision")
        graph.add_edge("stance_decision", "reflection")
        graph.add_edge("reflection", "speech_generate")
        graph.add_edge("speech_generate", "fact_check")
        graph.add_conditional_edges(
            "fact_check",
            lambda state: (
                "publish_message"
                if state.get("facts_ok") or state.get("rewrite_count", 0) >= 2
                else "speech_generate"
            ),
            {"publish_message": "publish_message", "speech_generate": "speech_generate"},
        )
        graph.add_edge("publish_message", "judge_score")
        graph.add_edge("judge_score", "turn_router")
        graph.add_edge("turn_router", END)
        return graph.compile()

    async def run_turn(self, debate: DebateState) -> DebateState:
        return await self.run_turn_streaming(debate, on_event=None)

    async def _emit(self, on_event: EventCallback | None, payload: dict[str, Any]) -> None:
        if on_event is None:
            return
        result = on_event(payload)
        if asyncio.iscoroutine(result):
            await result

    async def run_turn_streaming(
        self,
        debate: DebateState,
        *,
        on_event: EventCallback | None = None,
    ) -> DebateState:
        from app.services.debate_schedule_meta import advance_procedural_turn, is_procedural_segment

        if is_procedural_segment(debate):
            return advance_procedural_turn(debate)

        state: dict[str, Any] = {
            "debate": debate,
            "sources": [],
            "facts_ok": True,
            "rewrite_count": 0,
            "pipeline_started": False,
            "on_event": on_event,
            "reflection_draft": None,
            "reflection_polished": None,
        }
        if self.graph is not None:
            state = await self.graph.ainvoke(state)
        else:
            for step in (
                self._rag_retrieve,
                self._opening_evidence_retrieve,
                self._strategy_plan,
                self._stance_decision,
                self._reflection,
                self._speech_generate_streaming,
                self._fact_check,
                self._publish_message,
                self._judge_score,
                self._turn_router,
            ):
                state = await step(state)
        return state["debate"]

    def _mark(self, debate: DebateState, node_id: str, detail: str = ""):
        if node_id == "reflection":
            phase_node = "reflection_draft_finalize"
        else:
            phase_node = {
            ("rag_retrieve", "opening_prep"): "opening_evidence_bank",
            ("rag_retrieve", "argument_review"): "rag_retrieve",
            ("rag_retrieve", "rebuttal_review"): "rag_retrieve",
            ("rag_retrieve", "free_prep"): "rag_opponent_predict",
            ("rag_retrieve", "free_review"): "rag_realtime_rebuttal",
            ("rag_retrieve", "closing_prep"): "rag_full_knowledge",
            ("rag_retrieve", "closing_review"): "rag_closing_template",
            ("rag_retrieve", "post_match"): "rag_judge_criteria",
            ("opening_evidence_retrieve", "opening_prep"): "opening_evidence_bank",
            ("strategy_plan", "opening_prep"): "team_opening_discussion",
            ("strategy_plan", "free_prep"): "team_free_discussion",
            ("strategy_plan", "closing_prep"): "team_closing_discussion",
            ("stance_decision", "opening_prep"): "task_reason_check",
            ("stance_decision", "free_prep"): "free_strategy_check",
            ("speech_generate", "free_debate"): "free_alternate_output",
            ("fact_check", "argument_review"): "argument_strength_check",
            ("fact_check", "rebuttal_review"): "rebuttal_effect_check",
            ("fact_check", "closing_review"): "closing_quality_check",
            ("fact_check", "post_match"): "winner_decision",
            }.get((node_id, debate.phase), node_id)
        active_node = None
        for node in debate.workflow:
            if node.status == "running":
                node.status = "done"
            if node.id == phase_node:
                node.status = "running"
                if detail:
                    node.detail = detail
                active_node = node
        return active_node

    def _workflow_progress_payload(self, debate: DebateState, *, agent=None) -> dict[str, Any]:
        node = next((item for item in debate.workflow if item.status == "running"), None)
        if agent is None:
            agent = next((item for item in debate.agents if item.id == debate.active_speaker_id), None)
        return {
            "type": "workflow_progress",
            "node_id": node.id if node else "",
            "node_label": node.label if node else (debate.segment_label or debate.phase),
            "node_detail": node.detail if node else "",
            "segment_label": debate.segment_label,
            "phase": debate.phase,
            "speaker_id": agent.id if agent else debate.active_speaker_id,
            "speaker_name": agent.name if agent else (debate.active_speaker_id or "系统"),
            "side": agent.side if agent else "",
            "position": agent.position if agent else 0,
            "schedule_index": debate.schedule_index,
            "schedule_total": len(debate.schedule or []),
        }

    def _active_agent(self, debate: DebateState):
        agent = next((agent for agent in debate.agents if agent.id == debate.active_speaker_id), None)
        if agent is None:
            raise ValueError(f"Active speaker {debate.active_speaker_id!r} is not in debate agents")
        return agent

    async def _rag_retrieve(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        self._mark(debate, "rag_retrieve", "正在检索可引用资料与历史论点。")
        agent = self._active_agent(debate)
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=agent))
        segment_id = current_segment_id(debate)
        if (
            _is_internal_team_phase(debate.phase)
            and segment_id != "opening_evidence_bank"
            and segment_id not in RAG_SEGMENT_IDS
        ):
            state["sources"] = []
            return state
        if (
            not _is_public_debate_phase(debate.phase)
            and segment_id not in RAG_SEGMENT_IDS
            and segment_id != "opening_evidence_bank"
        ):
            state["sources"] = []
            return state
        viewer_side = agent.side if agent.side in {"affirmative", "negative"} else "judge"
        in_internal = _is_internal_team_phase(debate.phase)
        last_visible = latest_any_visible_message(
            debate.messages,
            viewer_side,
            in_internal_phase=in_internal,
        )
        query = (last_visible.content if last_visible else None) or debate.topic
        if segment_id == "opening_evidence_bank":
            state["sources"] = []
            return state
        state["sources"] = retrieve_sources(debate.topic, query, debate_id=debate.id)
        if state["sources"] and _is_public_debate_phase(debate.phase):
            add_sources_to_argument_bank(debate, state["sources"])
        return state

    async def _opening_evidence_retrieve(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if not needs_opening_evidence(debate):
            return state
        self._mark(debate, "opening_evidence_retrieve", "正在按正反方分别检索真实事实、案例和数据，并写入论据库。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))

        async def on_progress(detail: str) -> None:
            self._mark(debate, "opening_evidence_retrieve", detail)
            await self._emit(
                state.get("on_event"),
                self._workflow_progress_payload(debate, agent=self._active_agent(debate)),
            )

        result = await ensure_opening_argument_bank(
            debate,
            on_event=state.get("on_event"),
            on_progress=on_progress,
        )
        state["sources"] = result.sources
        if not opening_argument_bank_ready(debate):
            debate.auto_running = False
            debate.awaiting_user = False
            state["opening_evidence_blocked"] = True
            self._mark(debate, "opening_evidence_retrieve", "论据库尚未就绪，暂停在本节点等待后台预搜集完成。")
            await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        return state

    async def _strategy_plan(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            state["strategy"] = ""
            return state
        self._mark(debate, "strategy_plan", "快速生成本环节攻防路线。")
        agent = self._active_agent(debate)
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=agent))
        if agent.side == "affirmative":
            side_focus = f"围绕辩题「{debate.topic}」维护正方立场"
        elif agent.side == "negative":
            side_focus = f"围绕辩题「{debate.topic}」维护反方立场"
        else:
            side_focus = "保持中立，按规则判断双方表现"
        phase_focus = {
            "opening_prep": "分配立论任务，确认论点与论据。",
            "opening_statement": "先立标准，再给出主论点。",
            "argument_review": "评估刚才发言的强度与证据缺口。",
            "rebuttal": "直接回应上一轮最强论点，不铺陈背景。",
            "rebuttal_review": "判断驳论是否击中对方核心。",
            "cross_examination": "按质辩规则向指定辩手提一个问题，或只回答上一问。",
            "segment_summary": "三辩收束质辩战场，列出对方未回答问题。",
            "free_prep": "预测对手并安排短句攻防。",
            "free_debate": "只用一句话回应上一点或提出一个攻击点。",
            "free_review": "判断自由辩论是否应当收束。",
            "closing_prep": "汇总全场材料并确认总结框架。",
            "closing": "总结胜负标准并升华价值。",
            "closing_review": "判断总结陈词质量。",
            "pre_match": "主持开场，清楚说明规则。",
            "post_match": "裁决并点评双方表现。",
        }.get(debate.phase, "回应当前争点。")
        state["strategy"] = f"{side_focus}；{phase_focus}"
        return state

    async def _stance_decision(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            state["stance_action"] = "等待论据库"
            return state
        self._mark(debate, "stance_decision", "根据 4v4 赛制判断本轮发言任务。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        action_by_phase = {
            "pre_match": "主持",
            "opening_prep": "立论准备",
            "opening_statement": "开篇立论",
            "argument_review": "论点强度判断",
            "rebuttal": "驳论",
            "rebuttal_review": "驳论有效性判断",
            "cross_examination": "质辩",
            "segment_summary": "质辩小结",
            "free_prep": "自由辩论准备",
            "free_debate": "自由辩论",
            "free_review": "自由辩论复盘",
            "closing_prep": "总结准备",
            "closing": "总结陈词",
            "closing_review": "总结质量判断",
            "post_match": "裁决",
        }
        state["stance_action"] = action_by_phase.get(debate.phase, "回应")
        return state

    def _speech_user_content(self, debate: DebateState, state: dict) -> str:
        sources: list[Source] = state["sources"]
        agent = self._active_agent(debate)
        context = build_ai_debater_context(debate, agent, sources)
        no_repeat_note = ""
        if _is_internal_team_phase(debate.phase):
            no_repeat_note = (
                "\n当前处于队内交流：若上一条已是任务分配，本条必须改为短句接话与补充，不得逐段复述分工。"
            )
        return (
            f"辩题：{debate.topic}\n环节规则：{debate.segment_rules}\n"
            f"本轮任务：{state.get('stance_action', '发言')}\n"
            f"策略：{state.get('strategy', '')}\n"
            f"上一位对手公开发言（需优先回应；不含对方队内密谈）：\n{context.opponent_last}\n"
            f"对手上一条是否低信息量/明显让步：{'是' if context.opponent_last_is_low_information else '否'}\n"
            f"我方最近发言（避免与我方重复）：\n{context.self_last}\n"
            f"我方可用论据库：\n{format_argument_bank(context.own_argument_bank)}\n"
            f"对方可见论据库：\n{format_argument_bank(context.opponent_argument_bank)}\n"
            f"可参考事实（只作为底层依据，不要逐条复述）：\n{context.source_text}\n"
            f"辩论历史（仅含你方可见内容）：\n{context.visible_history}\n"
            f"发送策略：{'；'.join(context.policy_notes) or '按当前可见性发送数据。'}"
            f"{no_repeat_note}"
        )

    def _speech_messages(self, debate: DebateState, state: dict, agent) -> tuple[list[dict[str, str]], list[Source]]:
        sources: list[Source] = state["sources"]
        if debate.phase == "free_debate":
            length_hint = "自由辩论：只输出 1 句话，直击一个争点，不要分点或换行。"
        elif debate.phase == "opening_statement":
            arg_prefix = "AFF" if agent.side == "affirmative" else "NEG"
            all_argument_ids = _argument_ids_for_prompt(debate, agent.side)
            length_hint = (
                "开篇立论：发言总字数必须控制在 800 到 1000 个汉字。"
                "必须包含三个明确论点，每个论点配具体真实论据（非常识性推断）；"
                f"必须覆盖本方论据库全部条目，至少逐一引用这些论据 ID：{all_argument_ids}；"
                f"每条论据必须标注本方论据 ID，例如 [{arg_prefix}-1]；"
                "结构为：概念定义→论点一→论点二→论点三→价值升华收束。"
                "字数少于800字或多于1000字均视为发言不合格。"
            )
            if agent.side == "negative" and getattr(agent, "position", 0) == 1:
                length_hint += "反方一辩以建立反方立论为主，只允许少量回应正方框架，不得把整篇写成驳论。"
        elif debate.phase == "cross_examination":
            cross_mode = _cross_examination_mode(debate.segment_label or "")
            if cross_mode == "question":
                length_hint = (
                    "质辩提问：只提出 1 个问题，必须面向规则里指定的回答方。"
                    "问题以「请问」开头，15 秒内能说完，不要铺陈背景，不要替对方回答。"
                )
            else:
                length_hint = (
                    "质辩回答：只回答上一位三辩刚提出的 1 个问题，必须以本席位身份作答。"
                    "30 秒内说完，正面回应，不得反问、不得转移到长篇立论。"
                )
        elif _is_internal_team_phase(debate.phase):
            if _is_task_assign_segment(debate.segment_label):
                length_hint = (
                    "任务分配节点：只向队友交代分工，6 句以内。"
                    "格式：先 2-3 条核心分工，再给二/三/四辩各 1 条短任务。"
                    "严禁写成正式立论稿、严禁称呼主席/评委/对方辩友、严禁完整论证。"
                )
            else:
                length_hint = (
                    "队内讨论节点：每名未发言辩手会作为独立 API 调用发言。"
                    "当前调用只代表当前辩手本人，每位辩手在本段队内讨论中只发言一次。"
                    "发言集中研讨如何合理利用本方论据库和规划辩论策略，不要写成公开立论。"
                )
        elif agent.side in {"judge", "assistant"}:
            if debate.phase == "pre_match":
                if _has_prior_judge_pre_match(debate):
                    length_hint = "仅 1-2 句补充，勿重复欢迎、辩题定义与规则说明。"
                else:
                    length_hint = (
                        "主持开场（全场仅此一次）：欢迎→辩题争点→胜负标准→正反分工→下一环节；"
                        "120-200 字，勿冗长复述。"
                    )
            else:
                length_hint = "流程/判断节点：输出 2-5 句，说明结论和下一步，不要长篇。"
        elif debate.phase in {"rebuttal", "segment_summary"}:
            length_hint = f"本环节约 {debate.segment_seconds} 秒，发言控制在 3-5 句精炼语句，直击核心，不要长篇铺垫。"
        else:
            length_hint = f"本环节限时约 {debate.segment_seconds} 秒，请控制篇幅。"
        if _is_internal_team_phase(debate.phase) and agent.side in {"affirmative", "negative"}:
            team_name = "正方" if agent.side == "affirmative" else "反方"
            speaker_style = (
                f"你在{team_name}队内讨论窗口发言，只对本方队友说话，不面向评委和对方。"
                "严禁引用、驳斥或提及对方队内尚未公开的准备内容；"
                "若对方尚无公开发言，只按辩题与赛制分配本方任务，不要假装已听过对方立论。"
                "语气要口语化，像现场队友快速接话，不要公文腔。"
            )
        elif agent.side in {"affirmative", "negative"}:
            speaker_style = (
                "你正在真实辩论赛现场发言，要像人类辩手：先称呼主席、评委、对方辩友；"
                "用短句推进、用转折承接、用比较标准打战场，不要像说明文或百科条目。"
                "避免「综上所述，人工智能时代」这类模板句；每段都要有明确攻防动作。"
            )
        else:
            speaker_style = "你是中立裁判，请只做规则核对、评分依据说明和胜负判断，不要给任何一方策略指导。"
        cross_format = ""
        if debate.phase == "cross_examination":
            if _cross_examination_mode(debate.segment_label or "") == "question":
                cross_format = (
                    "必须使用 Markdown 二级标题 `## 质辩提问`；"
                    "正文只写一个以「请问」开头的问题，不得编号多问，不要自答。"
                )
            else:
                cross_format = (
                    "必须使用 Markdown 二级标题 `## 质辩回答`；"
                    "正文只回答上一问，先给直接答案，再用一两句理由支撑。"
                )
        if _is_internal_team_phase(debate.phase):
            response_rule = "队内讨论只接本方队友的话，不得写公开发言、不得称呼主席或评委。"
            citation_rule = "资料只作内部底稿，不在队内短句里堆引用编号。"
        elif agent.side in {"judge", "assistant"}:
            response_rule = "裁判不得替任何一方设计攻防路线，只能主持流程、说明规则、评价表现或裁决。"
            citation_rule = "如引用资料，只能用于解释裁判依据，不得给任一方补论据。"
        else:
            response_rule = (
                "先从对手最近一条发言中提取一到三个关键词或核心主张，逐一点名回应；"
                "若对手发言明显空泛/让步，需明确指出并转化为你方优势。"
                "若对方提出了多个论点，必须逐一点名回应，不得选择性忽视任何一条主论点。"
                "格式：先回应关键词 → 再推进己方论点。"
            )
            if debate.argument_bank_locked:
                citation_rule = "知识性事实、数据、报告和案例必须来自本方论据库，并在对应论据后标注本方论据 ID，例如 [AFF-1] 或 [NEG-1]；不得使用论据库外的新事实。"
            else:
                citation_rule = "引用下方检索资料时，请在论据后标注【资料标题】（与列表标题完全一致），勿编造未列出的资料名。"
        messages = [
            {
                "role": "system",
                "content": (
                    f"你是{agent.name}（{debate.segment_label}），{agent.persona}。"
                    f"{speaker_style}"
                    f"{cross_format}"
                    f"{segment_prompt_hint(debate)} {length_hint} "
                    "必须输出 Markdown 文本给前端渲染，正文尽量使用自然段。不要使用破折号，不要用星号粗体，不要堆叠符号；除非盘问环节必须编号，否则少用分点。"
                    "语言要适合朗读，句子流畅，转折用普通逗号和句号承接。"
                    "必须写完整段发言再结束，不要中途截断；至少有一个完整收束句，不要停在「一旦、如果、第三、包括」等半句话。"
                    "严格遵守身份边界：正反方只代表本方立场；裁判只做中立评判，不提供战术建议，不替任何一方写稿。"
                    "不要说「我是某某」。不要提 RAG、工作流、幻觉、可验证来源、资料库这些系统词。"
                    "每个主要论点必须配一个具体真实事例，格式为「xx机构/xx年xx研究表明：xxx」或「xx年xx事件：xxx」；"
                    "若无可靠来源，必须明确说明「根据常识推断」，严禁直接断言具体数字；"
                    "禁止编造机构名称、论文标题、具体统计数字；引用数据须有明确出处格式。"
                    f"{response_rule}"
                    f"{citation_rule}"
                    "自由辩论和队内讨论优先用短句口语，不要官样长句。"
                ),
            },
            {
                "role": "user",
                "content": self._speech_user_content(debate, state),
            },
        ]
        return messages, sources

    async def _reflection(self, state: dict) -> dict:
        """非自由辩论：一轮「草稿→定稿」；自由辩论跳过。"""
        debate: DebateState = state["debate"]
        on_event: EventCallback | None = state.get("on_event")
        state["reflection_draft"] = None
        state["reflection_polished"] = None

        if state.get("opening_evidence_blocked"):
            return state

        if debate.phase == "free_debate":
            self._mark(debate, "reflection", "自由辩论：跳过草稿→定稿反思。")
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
            return state

        if debate.phase == "pre_match":
            self._mark(debate, "reflection", "赛前主持：跳过草稿→定稿反思。")
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
            return state

        if _is_internal_team_phase(debate.phase):
            self._mark(debate, "reflection", "队内准备：跳过正式发言反思链。")
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
            return state

        if debate.phase == "post_match":
            self._mark(debate, "reflection", "裁判终局：跳过辩手草稿反思链。")
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
            return state

        self._mark(debate, "reflection", "草稿→定稿：内部一轮反思。")
        agent = self._active_agent(debate)
        await self._emit(on_event, self._workflow_progress_payload(debate, agent=agent))
        user_block = self._speech_user_content(debate, state)
        model = resolve_model(phase=debate.phase, speaker_id=agent.id)

        draft_system = (
            f"你是{agent.name}的内部辩论撰稿助手，与辩手立场完全一致。"
            "本轮只输出内部用草稿，绝不作为对评委或对方的终稿宣读。"
            "用 Markdown 精简写出：核心争点、我方要打的要点、2-3 个论证或事实抓手、预计如何收口。"
            "总字数约 180-320 字；不要开场寒暄称呼，不要写成完整发言稿。"
            "禁止编造法规、论文与具体统计数据；证据不足时请写“待查证/常识推断”。"
        )
        draft_messages: list[dict[str, str]] = [
            {"role": "system", "content": draft_system},
            {"role": "user", "content": user_block},
        ]

        draft_text = ""
        try:
            draft_text = (
                await chat_completion(
                    draft_messages,
                    model=model,
                    temperature=0.62,
                    max_tokens=520,
                    debate_id=debate.id,
                    operation="reflection_draft",
                )
            ).strip()
        except DeepSeekError:
            draft_text = ""

        if draft_text:
            state["reflection_draft"] = draft_text
        else:
            state["reflection_polished"] = None
            return state

        speech_messages, _ = self._speech_messages(debate, state, agent)
        speech_system = speech_messages[0]["content"]
        finalize_user = (
            f"{user_block}\n\n---\n【内部草稿】\n{draft_text}\n---\n"
            "请将以上草稿发展并改写为本轮要宣读的正式发言终稿（可调整结构与措辞，不要简单复读草稿小标题）。"
            "须满足与上文 system 角色说明中完全一致的身份、风格、篇幅与 Markdown 要求，并有一句完整收束。"
        )
        finalize_messages: list[dict[str, str]] = [
            {"role": "system", "content": speech_system},
            {"role": "user", "content": finalize_user},
        ]

        polished = ""
        try:
            polished = (
                await chat_completion(
                    finalize_messages,
                    model=model,
                    temperature=0.68,
                    max_tokens=_max_tokens_for_phase(debate.phase),
                    debate_id=debate.id,
                    operation="reflection_finalize",
                )
            ).strip()
        except DeepSeekError:
            polished = ""

        state["reflection_polished"] = polished or None

        await self._emit(
            on_event,
            {
                "type": "reflection_done",
                "phase": debate.phase,
                "draft_chars": len(draft_text),
                "polished_chars": len(state["reflection_polished"] or ""),
            },
        )
        return state

    def _speech_chunk_payload(
        self,
        *,
        message_id: str,
        chunk: str,
        content: str,
        debate: DebateState,
        agent,
    ) -> dict[str, Any]:
        return {
            "type": "speech_chunk",
            "message_id": message_id,
            "chunk": chunk,
            "content": content,
            "speaker_id": agent.id,
            "speaker_name": agent.name,
            "side": agent.side,
            "phase": debate.phase,
            "segment_label": debate.segment_label,
        }

    async def _emit_precomputed_speech_chunks(
        self,
        *,
        text: str,
        on_event: EventCallback | None,
        message_id: str,
        debate: DebateState,
        state: dict[str, Any],
        agent,
    ) -> str:
        text = strip_model_reasoning(text)
        content = ""
        step = 56
        for i in range(0, len(text), step):
            chunk = text[i : i + step]
            content += chunk
            await self._emit(
                on_event,
                self._speech_chunk_payload(
                    message_id=message_id,
                    chunk=chunk,
                    content=content,
                    debate=debate,
                    agent=agent,
                ),
            )
            if len(content) >= 80 and not state.get("pipeline_started"):
                state["pipeline_started"] = True
                asyncio.create_task(self._prepare_next_pipeline(debate, content, on_event))
            await asyncio.sleep(0.035)
        return content

    async def _complete_if_needed(
        self,
        *,
        content: str,
        messages: list[dict[str, str]],
        model: str,
        on_event: EventCallback | None,
        message_id: str,
        debate: DebateState,
        agent,
    ) -> str:
        target_chars = _completion_target_chars(debate)
        normalized = re.sub(r"\s+", "", strip_model_reasoning(content or ""))
        if _has_substantive_completion(content, debate) and (
            not target_chars or len(normalized) >= target_chars
        ):
            return content
        completed = strip_model_reasoning(content or "")
        max_rounds = 3 if debate.phase == "opening_statement" else 1
        for _ in range(max_rounds):
            normalized = re.sub(r"\s+", "", completed)
            if _has_substantive_completion(completed, debate) and (
                not target_chars or len(normalized) >= target_chars
            ):
                break
            remaining_note = (
                f"当前约 {len(normalized)} 字，目标至少 {target_chars} 字。"
                if target_chars
                else "当前内容仍不足。"
            )
            continuation_prompt = [
                *messages,
                {
                    "role": "assistant",
                    "content": completed,
                },
                {
                    "role": "user",
                    "content": (
                        "上面的发言尚未写完，或虽然有标点但内容过短、不足以完成当前环节。"
                        f"{remaining_note}"
                        "请只续写缺失部分，补全已宣布的论证框架或质辩问答任务，并用完整收束句结束；不要重复已经写过的内容。"
                    ),
                },
            ]
            try:
                extra = await chat_completion(
                    continuation_prompt,
                    model=model,
                    temperature=0.55,
                    max_tokens=min(2400, _max_tokens_for_phase(debate.phase)),
                    debate_id=debate.id,
                    operation="speech_continuation",
                )
            except DeepSeekError:
                extra = "因此，这一点要立刻收束为可执行的攻防任务，避免停在半句上。"
            extra = strip_model_reasoning(extra or "")
            if not extra:
                break
            separator = "\n\n" if completed and not completed.endswith(("\n", " ")) else ""
            completed = strip_model_reasoning(f"{completed}{separator}{extra.strip()}")
            await self._emit(
                on_event,
                self._speech_chunk_payload(
                    message_id=message_id,
                    chunk=extra,
                    content=completed,
                    debate=debate,
                    agent=agent,
                ),
            )
        return completed

    async def _prepare_next_pipeline(self, debate: DebateState, partial: str, on_event: EventCallback | None) -> None:
        next_id = peek_next_speaker_id(debate)
        if not next_id or next_id == "judge":
            return
        next_agent = next((a for a in debate.agents if a.id == next_id), None)
        if not next_agent:
            return
        query = f"{debate.topic}\n当前发言片段：{partial[-400:]}"
        sources = retrieve_sources(debate.topic, query, debate_id=debate.id)
        await self._emit(
            on_event,
            {
                "type": "pipeline_prep",
                "next_speaker_id": next_id,
                "next_speaker_name": next_agent.name,
                "partial_length": len(partial),
                "sources_count": len(sources),
            },
        )

    async def _team_discussion_generate(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        on_event: EventCallback | None = state.get("on_event")
        agent = self._active_agent(debate)
        self._mark(debate, "speech_generate", "队内讨论：每位未发言辩手独立调用并只发言一次。")
        await self._emit(on_event, self._workflow_progress_payload(debate, agent=agent))
        private_thought = f"内部策略：{state.get('strategy', '')}"
        messages: list[DebateMessage] = []
        context = TeamDiscussionContext(
            stance_action=state.get("stance_action", "队内讨论"),
            strategy=state.get("strategy", ""),
            sources=state.get("sources") or [],
        )
        for teammate in team_discussion_speakers(debate, agent):
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=teammate))
            draft = await generate_team_discussion_draft(
                debate,
                context,
                teammate,
                chat_completion_fn=chat_completion,
            )
            message_id = str(uuid4())
            await self._emit(
                on_event,
                {
                    "type": "speech_start",
                    "message_id": message_id,
                    "speaker_id": teammate.id,
                    "speaker_name": teammate.name,
                    "side": teammate.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            await self._emit(
                on_event,
                self._speech_chunk_payload(
                    message_id=message_id,
                    chunk=draft.content,
                    content=draft.content,
                    debate=debate,
                    agent=teammate,
                ),
            )
            await self._emit(
                on_event,
                {
                    "type": "speech_end",
                    "message_id": message_id,
                    "content": draft.content,
                    "speaker_id": teammate.id,
                    "speaker_name": teammate.name,
                    "side": teammate.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            messages.append(
                DebateMessage(
                    id=message_id,
                    debate_id=debate.id,
                    speaker_id=teammate.id,
                    speaker_name=teammate.name,
                    side=teammate.side,
                    content=draft.content,
                    phase=debate.phase,
                    segment_label=debate.segment_label,
                    sources=[],
                    private_thought=private_thought,
                    strategy=state.get("strategy"),
                )
            )
        state["draft_messages"] = messages
        state["draft_message"] = messages[-1] if messages else None
        state["rewrite_count"] = state.get("rewrite_count", 0) + 1
        return state

    async def _speech_generate_streaming(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        on_event: EventCallback | None = state.get("on_event")
        if state.get("opening_evidence_blocked"):
            state["draft_message"] = None
            state["rewrite_count"] = state.get("rewrite_count", 0) + 1
            return state
        if _is_team_discussion_segment(debate) and not _is_task_assign_segment(debate.segment_label):
            return await self._team_discussion_generate(state)
        if debate.phase == "opening_prep" and "真实论据入库" in (debate.segment_label or ""):
            agent = self._active_agent(debate)
            message_id = str(uuid4())
            aff_count = argument_count_for_side(debate, "affirmative")
            neg_count = argument_count_for_side(debate, "negative")
            content = (
                f"论据库已完成赛前入库：正方 {aff_count} 条，反方 {neg_count} 条。"
                "接下来的队内讨论将围绕这些论据规划立论策略。"
            )
            await self._emit(
                on_event,
                {
                    "type": "speech_start",
                    "message_id": message_id,
                    "speaker_id": agent.id,
                    "speaker_name": agent.name,
                    "side": agent.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            await self._emit(
                on_event,
                self._speech_chunk_payload(
                    message_id=message_id,
                    chunk=content,
                    content=content,
                    debate=debate,
                    agent=agent,
                ),
            )
            await self._emit(
                on_event,
                {
                    "type": "speech_end",
                    "message_id": message_id,
                    "content": content,
                    "speaker_id": agent.id,
                    "speaker_name": agent.name,
                    "side": agent.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            state["draft_message"] = DebateMessage(
                id=message_id,
                debate_id=debate.id,
                speaker_id=agent.id,
                speaker_name=agent.name,
                side=agent.side,
                content=content,
                phase=debate.phase,
                segment_label=debate.segment_label,
                sources=[],
                private_thought="裁判确认论据库赛前入库完成。",
                strategy=state.get("strategy"),
            )
            state["rewrite_count"] = state.get("rewrite_count", 0) + 1
            return state
        if state.get("rewrite_count", 0) >= 1:
            state["reflection_polished"] = None

        polished: str | None = state.get("reflection_polished")
        use_reflection_output = bool(polished)

        if use_reflection_output:
            self._mark(debate, "speech_generate", "播送反思后的定稿发言。")
        else:
            self._mark(debate, "speech_generate", "DeepSeek 正在流式生成 Markdown 发言。")
        agent = self._active_agent(debate)
        await self._emit(on_event, self._workflow_progress_payload(debate, agent=agent))
        messages, sources = self._speech_messages(debate, state, agent)
        model = resolve_model(phase=debate.phase, speaker_id=agent.id)
        message_id = str(uuid4())
        content = ""
        raw_content = ""

        if agent.side == "judge" and "输出裁判报告" in (debate.segment_label or ""):
            self._mark(debate, "speech_generate", "裁判正在生成终局报告。")
            await self._emit(on_event, self._workflow_progress_payload(debate, agent=agent))
            content = strip_model_reasoning(await generate_final_report(debate))
            state["final_report_generated"] = True
            await self._emit(
                on_event,
                {
                    "type": "speech_start",
                    "message_id": message_id,
                    "speaker_id": agent.id,
                    "speaker_name": agent.name,
                    "side": agent.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            await self._emit(
                on_event,
                self._speech_chunk_payload(
                    message_id=message_id,
                    chunk=content,
                    content=content,
                    debate=debate,
                    agent=agent,
                ),
            )
            await self._emit(
                on_event,
                {
                    "type": "speech_end",
                    "message_id": message_id,
                    "content": content,
                    "speaker_id": agent.id,
                    "speaker_name": agent.name,
                    "side": agent.side,
                    "phase": debate.phase,
                    "segment_label": debate.segment_label,
                },
            )
            state["draft_message"] = DebateMessage(
                id=message_id,
                debate_id=debate.id,
                speaker_id=agent.id,
                speaker_name=agent.name,
                side=agent.side,
                content=content,
                phase=debate.phase,
                segment_label=debate.segment_label,
                sources=[],
                private_thought="裁判终局报告",
                strategy=state.get("strategy"),
            )
            state["rewrite_count"] = state.get("rewrite_count", 0) + 1
            return state

        await self._emit(
            on_event,
            {
                "type": "speech_start",
                "message_id": message_id,
                "speaker_id": agent.id,
                "speaker_name": agent.name,
                "side": agent.side,
                "phase": debate.phase,
                "segment_label": debate.segment_label,
            },
        )

        if use_reflection_output and polished:
            content = strip_model_reasoning(polished)
            content = await self._complete_if_needed(
                content=content,
                messages=messages,
                model=model,
                on_event=on_event,
                message_id=message_id,
                debate=debate,
                agent=agent,
            )
            content = _apply_phase_speech_limits(content, debate)
            content = await self._emit_precomputed_speech_chunks(
                text=content,
                on_event=on_event,
                message_id=message_id,
                debate=debate,
                state=state,
                agent=agent,
            )
        else:
            try:
                async for chunk in chat_completion_stream(
                    messages,
                    model=model,
                    temperature=0.75 if debate.phase != "free_debate" else 0.85,
                    max_tokens=_max_tokens_for_phase(debate.phase),
                    debate_id=debate.id,
                    operation="speech_stream",
                ):
                    raw_content += chunk
                    cleaned = strip_model_reasoning(raw_content)
                    if cleaned == content:
                        continue
                    chunk = cleaned[len(content) :]
                    content = cleaned
                    await self._emit(
                        on_event,
                        self._speech_chunk_payload(
                            message_id=message_id,
                            chunk=chunk,
                            content=content,
                            debate=debate,
                            agent=agent,
                        ),
                    )
                    if len(content) >= 80 and not state.get("pipeline_started"):
                        state["pipeline_started"] = True
                        asyncio.create_task(self._prepare_next_pipeline(debate, content, on_event))
            except DeepSeekError as exc:
                if debate.phase == "free_debate":
                    content = "对方把“能用”偷换成“会提升”。如果学生只是复制答案，学习能力反而是在退步。"
                elif agent.side == "affirmative":
                    content = "主席、各位评委，对方忽略了一个前提：工具不会自动替代思考，关键在于如何使用。"
                elif agent.side == "judge":
                    content = "裁判记录：当前回合模型暂不可用，本条仅作中立过程记录，不计入任一方优势。"
                else:
                    content = "主席、各位评委，我方要提醒对方：效率提升不等于能力提升。"
                content += f"\n\n（模型暂不可用：{exc}）"
                content = strip_model_reasoning(content)
                await self._emit(
                    on_event,
                    self._speech_chunk_payload(
                        message_id=message_id,
                        chunk=content,
                        content=content,
                        debate=debate,
                        agent=agent,
                    ),
                )

        if not (use_reflection_output and polished):
            content = strip_model_reasoning(content)
            content = await self._complete_if_needed(
                content=content,
                messages=messages,
                model=model,
                on_event=on_event,
                message_id=message_id,
                debate=debate,
                agent=agent,
            )
            content = _apply_phase_speech_limits(content, debate)

        await self._emit(
            on_event,
            {
                "type": "speech_end",
                "message_id": message_id,
                "content": content,
                "speaker_id": agent.id,
                "speaker_name": agent.name,
                "side": agent.side,
                "phase": debate.phase,
                "segment_label": debate.segment_label,
            },
        )

        private_parts = [f"内部策略：{state.get('strategy', '')}"]
        rd = state.get("reflection_draft")
        if rd:
            suffix = "…" if len(rd) > 480 else ""
            private_parts.append(f"反思草稿：{rd[:480]}{suffix}")

        state["draft_message"] = DebateMessage(
            id=message_id,
            debate_id=debate.id,
            speaker_id=agent.id,
            speaker_name=agent.name,
            side=agent.side,
            content=content,
            phase=debate.phase,
            segment_label=debate.segment_label,
            sources=sources,
            private_thought=" | ".join(private_parts),
            strategy=state.get("strategy"),
        )
        state["rewrite_count"] = state.get("rewrite_count", 0) + 1
        return state

    async def _speech_generate(self, state: dict) -> dict:
        return await self._speech_generate_streaming(state)

    async def _fact_check(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            state["facts_ok"] = True
            return state
        self._mark(debate, "fact_check", "快速检查发言是否含明显无来源断言。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        messages: list[DebateMessage] = state.get("draft_messages") or [state["draft_message"]]
        risky_terms = ("研究表明", "数据显示", "%", "法律规定", "论文指出")
        if not _is_public_debate_phase(debate.phase):
            for message in messages:
                if message is not None:
                    message.content = strip_model_reasoning(message.content)
                    message.hallucination_risk = "low"
            state["facts_ok"] = True
            return state
        facts_ok = True
        for message in messages:
            is_internal_discussion = _is_team_discussion_segment(debate) and message.side in {"affirmative", "negative"}
            if is_internal_discussion:
                message.content = strip_model_reasoning(message.content)
                unverified = False
            else:
                message.content = strip_model_reasoning(
                    _sanitize_content_preserving_argument_ids(message.content, message.sources)
                )
                unverified = _has_unverified_citations_preserving_argument_ids(message.content, message.sources)
            risky = any(term in message.content for term in risky_terms)
            missing_opening_bank_ids: set[str] = set()
            if message.phase == "opening_statement" and message.side in {"affirmative", "negative"}:
                required_ids = argument_ids_for_side(debate, message.side)
                if required_ids:
                    missing_opening_bank_ids = required_ids - referenced_argument_ids(message.content)
            if unverified or (risky and not message.sources):
                facts_ok = False
            if missing_opening_bank_ids:
                facts_ok = False
            # 设置幻觉风险等级供前端展示
            import re as _re
            has_sources = bool(message.sources)
            has_numbers = bool(_re.search(r'\d+[\.\d]*\s*%|\d{4}\s*年|\d+\s*(万|亿|项|人|次)', message.content))
            if unverified or (risky and not has_sources) or missing_opening_bank_ids:
                message.hallucination_risk = "high"
            elif risky and has_sources:
                message.hallucination_risk = "low"
            elif has_numbers and not has_sources:
                message.hallucination_risk = "medium"
            else:
                message.hallucination_risk = "low"
        state["facts_ok"] = facts_ok
        return state

    def _build_match_summary(self, debate: DebateState) -> str:
        public_phases = {
            "opening_statement",
            "rebuttal",
            "cross_examination",
            "segment_summary",
            "free_debate",
            "closing",
        }
        lines = [
            f"## 全场概览 · {debate.topic}",
            "",
            f"- 当前比分：正方 {debate.score.get('affirmative', 0):.1f} · 反方 {debate.score.get('negative', 0):.1f}",
            f"- 已完成环节：{debate.segment_label or debate.phase}",
            "",
            "### 关键交锋摘录",
            "",
        ]
        for message in debate.messages:
            if message.phase not in public_phases and message.side != "judge":
                continue
            if message.side not in {"affirmative", "negative", "judge"}:
                continue
            excerpt = (message.content or "").strip().replace("\n", " ")
            if len(excerpt) > 160:
                excerpt = excerpt[:160] + "…"
            if not excerpt:
                continue
            lines.append(f"- **{message.speaker_name}**（{message.segment_label or message.phase}）：{excerpt}")
        verdict = next(
            (
                m
                for m in reversed(debate.messages)
                if m.side == "judge" and "输出裁判报告" in (m.segment_label or "")
            ),
            None,
        )
        if verdict:
            lines.extend(["", "### 裁判终局报告", "", verdict.content.strip()])
        return "\n".join(lines).strip()

    async def _publish_message(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            debate.updated_at = utc_now()
            return state
        self._mark(debate, "publish_message", "写入长期记录并准备实时广播。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        messages: list[DebateMessage] = state.get("draft_messages") or [state["draft_message"]]
        for message in messages:
            if message is not None:
                debate.messages.append(message)
                if _is_public_debate_phase(message.phase) and message.sources:
                    await add_message_arguments_to_bank_with_ai_titles(debate, message)
        debate.updated_at = utc_now()
        label = (messages[-1].segment_label if messages and messages[-1] else debate.segment_label) or ""
        if "输出裁判报告" in label:
            report = messages[-1].content if state.get("final_report_generated") and messages else await generate_final_report(debate)
            debate.match_summary = report
            if messages and messages[-1] is not None:
                messages[-1].content = strip_model_reasoning(report)
        return state

    async def _judge_score(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            return state
        self._mark(debate, "judge_score", "裁判按逻辑、回应和证据进行快速评分。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        if _is_internal_team_phase(debate.phase):
            return state
        message: DebateMessage = debate.messages[-1]

        reasons: list[str] = ["环节基础 +1.20"]
        delta = 1.2
        source_bonus = min(len(message.sources), 3) * 0.15
        if source_bonus:
            delta += source_bonus
            reasons.append(f"可引用资料 {len(message.sources)} 条 +{source_bonus:.2f}")
        length_bonus = 0.2 if 40 <= len(message.content) <= 280 else 0
        if length_bonus:
            delta += length_bonus
            reasons.append(f"篇幅适中 +{length_bonus:.2f}")
        if not state.get("facts_ok", True):
            delta -= 0.8
            reasons.append("缺少可靠来源 -0.80")
        message.private_thought = (message.private_thought or "") + " | 裁判：回应明确，按本环节完成度计分。"
        message.score_reason = "；".join(reasons)

        if message.side in debate.score:
            debate.score[message.side] += delta
            message.score_delta = round(delta, 2)
        return state

    async def _turn_router(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        if state.get("opening_evidence_blocked"):
            debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)
            return state
        self._mark(debate, "turn_router", "按 4v4 标准赛制进入下一环节。")
        await self._emit(state.get("on_event"), self._workflow_progress_payload(debate, agent=self._active_agent(debate)))
        debate.turn_index += 1
        advance_schedule(debate)
        debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)
        return state


debate_graph = DebateGraph()
