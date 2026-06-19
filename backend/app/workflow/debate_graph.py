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
from app.services.argument_bank import add_argument_items, build_argument_bank_from_sources
from app.services.debate_mode import peek_next_speaker_id
from app.services.debate_schedule import advance_schedule, segment_prompt_hint
from app.services.llm import DeepSeekError, chat_completion, chat_completion_stream, resolve_model, strip_model_reasoning
from app.services.message_visibility import latest_any_visible_message
from app.services.judge_report import generate_final_report
from app.services.rag import retrieve_sources

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


def _is_internal_team_phase(phase: str) -> bool:
    return phase in {"opening_prep", "free_prep", "closing_prep"}


def _is_task_assign_segment(segment_label: str) -> bool:
    return "任务分配" in (segment_label or "")


def _is_team_discussion_segment(debate: DebateState) -> bool:
    return _is_internal_team_phase(debate.phase) and "队内讨论" in (debate.segment_label or "")


def _positions_spoken_in_segment(debate: DebateState, side: str) -> set[int]:
    from app.services.debate_mode import debate_user_position, debate_user_side

    positions: set[int] = set()
    label = debate.segment_label or ""
    for message in debate.messages:
        if message.side != side or message.segment_label != label:
            continue
        agent = next((a for a in debate.agents if a.id == message.speaker_id), None)
        if agent:
            positions.add(agent.position)
        elif message.speech_flag is not None and debate_user_side(debate) == side:
            positions.add(debate_user_position(debate))
    return positions


def _first_debater_already_assigned(debate: DebateState, side: str) -> bool:
    """一辩任务分配已完成后，队内讨论不再重复生成一辩发言。"""
    for message in reversed(debate.messages):
        if message.side != side:
            continue
        label = message.segment_label or ""
        if "任务分配" in label:
            return True
        if "队内讨论" in label:
            return False
    return False


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
    if "回应盘问" in label or "回应质询" in label:
        return "respond"
    if "盘问" in label or "质询" in label:
        return "question"
    return "respond"


class DebateGraph:
    """LangGraph agentic loop backed by DeepSeek."""

    def __init__(self) -> None:
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        if StateGraph is None:
            return None

        graph = StateGraph(dict)
        graph.add_node("rag_retrieve", self._rag_retrieve)
        graph.add_node("strategy_plan", self._strategy_plan)
        graph.add_node("stance_decision", self._stance_decision)
        graph.add_node("reflection", self._reflection)
        graph.add_node("speech_generate", self._speech_generate_streaming)
        graph.add_node("fact_check", self._fact_check)
        graph.add_node("publish_message", self._publish_message)
        graph.add_node("judge_score", self._judge_score)
        graph.add_node("turn_router", self._turn_router)

        graph.set_entry_point("rag_retrieve")
        graph.add_edge("rag_retrieve", "strategy_plan")
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

    def _mark(self, debate: DebateState, node_id: str, detail: str = "") -> None:
        if node_id == "reflection":
            phase_node = "reflection_draft_finalize"
        else:
            phase_node = {
            ("rag_retrieve", "opening_prep"): "rag_opening_args",
            ("rag_retrieve", "argument_review"): "rag_retrieve",
            ("rag_retrieve", "rebuttal_review"): "rag_retrieve",
            ("rag_retrieve", "free_prep"): "rag_opponent_predict",
            ("rag_retrieve", "free_review"): "rag_realtime_rebuttal",
            ("rag_retrieve", "closing_prep"): "rag_full_knowledge",
            ("rag_retrieve", "closing_review"): "rag_closing_template",
            ("rag_retrieve", "post_match"): "rag_judge_criteria",
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
        for node in debate.workflow:
            if node.status == "running":
                node.status = "done"
            if node.id == phase_node:
                node.status = "running"
                if detail:
                    node.detail = detail

    def _active_agent(self, debate: DebateState):
        agent = next((agent for agent in debate.agents if agent.id == debate.active_speaker_id), None)
        if agent is None:
            raise ValueError(f"Active speaker {debate.active_speaker_id!r} is not in debate agents")
        return agent

    async def _rag_retrieve(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        self._mark(debate, "rag_retrieve", "正在检索可引用资料与历史论点。")
        agent = self._active_agent(debate)
        viewer_side = agent.side if agent.side in {"affirmative", "negative"} else "judge"
        in_internal = _is_internal_team_phase(debate.phase)
        last_visible = latest_any_visible_message(
            debate.messages,
            viewer_side,
            in_internal_phase=in_internal,
        )
        query = (last_visible.content if last_visible else None) or debate.topic
        state["sources"] = retrieve_sources(debate.topic, query, debate_id=debate.id)
        if state["sources"] and not debate.argument_bank_locked:
            bank = build_argument_bank_from_sources(debate.topic, state["sources"])
            add_argument_items(debate, "affirmative", bank["affirmative"])
            add_argument_items(debate, "negative", bank["negative"])
        return state

    async def _strategy_plan(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        self._mark(debate, "strategy_plan", "快速生成本环节攻防路线。")
        agent = self._active_agent(debate)
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
            "cross_examination": "盘问方连续提问；回应方逐条作答，不得回避。",
            "segment_summary": "收束战场，列出对方未回答问题。",
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
        self._mark(debate, "stance_decision", "根据 4v4 赛制判断本轮发言任务。")
        action_by_phase = {
            "pre_match": "主持",
            "opening_prep": "立论准备",
            "opening_statement": "开篇立论",
            "argument_review": "论点强度判断",
            "rebuttal": "驳论",
            "rebuttal_review": "驳论有效性判断",
            "cross_examination": "盘问/质询",
            "segment_summary": "小结",
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
            length_hint = (
                "开篇立论：发言总字数不低于900字（约三分钟朗读时长）。"
                "必须包含三个明确论点，每个论点配一条具体真实论据（非常识性推断）；"
                f"每条论据必须标注论据 ID：[{arg_prefix}-1]、[{arg_prefix}-2]、[{arg_prefix}-3]；"
                "结构为：概念定义→论点一→论点二→论点三→价值升华收束。"
                "字数不足900字将视为发言未完成。"
            )
            if agent.side == "negative" and getattr(agent, "position", 0) == 1:
                length_hint += "反方一辩以建立反方立论为主，只允许少量回应正方框架，不得把整篇写成驳论。"
        elif debate.phase == "cross_examination":
            cross_mode = _cross_examination_mode(debate.segment_label or "")
            if cross_mode == "question":
                length_hint = "盘问环节：连续提出 2-4 个「请问」式问题，每条独立成段，不要替对方回答。"
            else:
                length_hint = "回应盘问：逐条对应回答上文质询，格式可用「第一问…」「第二问…」；控制在4-5句，简洁精炼。"
        elif _is_internal_team_phase(debate.phase):
            if _is_task_assign_segment(debate.segment_label):
                length_hint = (
                    "任务分配节点：只向队友交代分工，6 句以内。"
                    "格式：先 2-3 条核心分工，再给二/三/四辩各 1 条短任务。"
                    "严禁写成正式立论稿、严禁称呼主席/评委/对方辩友、严禁完整论证。"
                )
            else:
                length_hint = (
                    "队内讨论节点：必须体现二辩/三辩/四辩都在接话。"
                    "输出格式严格使用「一辩：…」「二辩：…」「三辩：…」「四辩：…」。"
                    "每人 1 句短句（口语化、能落地），总共 4-6 句，不要长段落。"
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
                    "必须使用 Markdown 二级标题 `## 质询`，下列 2-4 条编号问题；"
                    "每条以「请问」开头，独立成段，不要自答。"
                )
            else:
                cross_format = (
                    "必须使用 Markdown 二级标题 `## 回应盘问`，按「第一问/第二问…」逐条回应；"
                    "先回应对方质询，再简要反驳。"
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
            citation_rule = "引用下方检索资料时，请在论据后标注【资料标题】（与列表标题完全一致），勿编造未列出的资料名。"
        messages = [
            {
                "role": "system",
                "content": (
                    f"你是{agent.name}（{debate.segment_label}），{agent.persona}。"
                    f"{speaker_style}"
                    f"{cross_format}"
                    f"{segment_prompt_hint(debate)} {length_hint} "
                    "输出给前端 Markdown 渲染，但正文尽量使用自然段。不要使用破折号，不要用星号粗体，不要堆叠符号；除非盘问环节必须编号，否则少用分点。"
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

        if debate.phase == "free_debate":
            self._mark(debate, "reflection", "自由辩论：跳过草稿→定稿反思。")
            return state

        if debate.phase == "pre_match":
            self._mark(debate, "reflection", "赛前主持：跳过草稿→定稿反思。")
            return state

        if _is_internal_team_phase(debate.phase):
            self._mark(debate, "reflection", "队内准备：跳过正式发言反思链。")
            return state

        if debate.phase == "post_match":
            self._mark(debate, "reflection", "裁判终局：跳过辩手草稿反思链。")
            return state

        self._mark(debate, "reflection", "草稿→定稿：内部一轮反思。")
        agent = self._active_agent(debate)
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
        if not _looks_incomplete(content):
            return content
        continuation_prompt = [
            *messages,
            {
                "role": "assistant",
                "content": content,
            },
            {
                "role": "user",
                "content": (
                    "上面的发言尚未写完（可能在半句处停止，或只写了「第一」层/点却未写完后续层次）。"
                    "请只续写缺失部分，补全已宣布的论证框架，并用 1 句完整收束句结束；不要重复已经写过的内容。"
                ),
            },
        ]
        try:
            extra = await chat_completion(
                continuation_prompt,
                model=model,
                temperature=0.55,
                max_tokens=min(1200, _max_tokens_for_phase(debate.phase)),
                debate_id=debate.id,
                operation="speech_continuation",
            )
        except DeepSeekError:
            extra = "因此，这一点要立刻收束为可执行的攻防任务，避免停在半句上。"
        if not extra:
            return content
        extra = strip_model_reasoning(extra)
        if not extra:
            return content
        separator = "" if content.endswith((" ", "\n")) else ""
        completed = f"{content}{separator}{extra.strip()}"
        completed = strip_model_reasoning(completed)
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

    def _team_discussion_prompt(self, debate: DebateState, state: dict, agent) -> list[dict[str, str]]:
        side_label = "正方" if agent.side == "affirmative" else "反方"
        return [
            {
                "role": "system",
                "content": (
                    f"你正在生成{side_label}队内讨论，不是公开发言。"
                    "必须严格输出恰好四行，格式为「一辩：...」「二辩：...」「三辩：...」「四辩：...」，缺少任何一行均视为格式错误。"
                    "每位辩手只说1句短句，口语化，像现场队友快速确认分工。"
                    "二辩/三辩/四辩在接话时须明确引用一辩的框架，先表示认可，再补充不同维度（数据/案例/价值）；禁止四位辩手各说各话、互不衔接。"
                    "不得称呼主席、评委或对方辩友；不得写成正式立论、盘问或总结陈词。"
                    "不得编造数据、论文、法规；证据不足时只说常识推断或待查。"
                ),
            },
            {"role": "user", "content": self._speech_user_content(debate, state)},
        ]

    def _parse_team_discussion_lines(self, text: str, debate: DebateState, side: str) -> list[tuple[int, str]]:
        import logging as _logging
        cleaned = strip_model_reasoning(text)
        by_position: dict[int, str] = {}
        pattern = re.compile(r"([一二三四1234])辩\s*[:：]\s*([\s\S]*?)(?=(?:\n\s*)?[一二三四1234]辩\s*[:：]|$)")
        number_map = {"一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}
        for match in pattern.finditer(cleaned):
            position = number_map.get(match.group(1))
            content = re.sub(r"\s+", " ", match.group(2)).strip()
            if position and content:
                by_position[position] = _limit_sentences(content, 2)
        if len(by_position) < 4:
            missing = [p for p in range(1, 5) if p not in by_position]
            _logging.warning(
                "team_discussion parse: only %d/4 positions found (missing: %s) for debate=%s side=%s",
                len(by_position), missing, debate.id, side,
            )
        fallback = {
            1: "我先把本轮框架收住，大家围绕当前争点补强，不要跑偏。",
            2: "我负责补定义和反驳入口，用一个日常例子把逻辑讲清。",
            3: "我负责追问对方薄弱处，把问题压到可验证和可执行上。",
            4: "我负责最后收束标准，把我们这一边的胜负线讲稳。",
        }
        return [(position, by_position.get(position) or fallback[position]) for position in range(1, 5)]

    async def _team_discussion_generate(self, state: dict) -> dict:
        debate: DebateState = state["debate"]
        on_event: EventCallback | None = state.get("on_event")
        agent = self._active_agent(debate)
        model = resolve_model(phase=debate.phase, speaker_id=agent.id)
        self._mark(debate, "speech_generate", "队内讨论：四位辩手依次短句接话。")
        try:
            raw = await chat_completion(
                self._team_discussion_prompt(debate, state, agent),
                model=model,
                temperature=0.65,
                max_tokens=800,
                debate_id=debate.id,
                operation="team_discussion",
            )
        except DeepSeekError:
            raw = ""
        lines = self._parse_team_discussion_lines(raw, debate, agent.side)
        spoken = _positions_spoken_in_segment(debate, agent.side)
        if _first_debater_already_assigned(debate, agent.side):
            spoken.add(1)
        lines = [(position, content) for position, content in lines if position not in spoken]
        private_thought = f"内部策略：{state.get('strategy', '')}"
        messages: list[DebateMessage] = []
        prefix = "aff" if agent.side == "affirmative" else "neg"
        for position, content in lines:
            teammate = next((a for a in debate.agents if a.side == agent.side and a.position == position), None)
            if teammate is None:
                continue
            message_id = str(uuid4())
            await self._emit(
                on_event,
                {
                    "type": "speech_start",
                    "message_id": message_id,
                    "speaker_id": f"{prefix}_{position}",
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
                    chunk=content,
                    content=content,
                    debate=debate,
                    agent=teammate,
                ),
            )
            await self._emit(
                on_event,
                {
                    "type": "speech_end",
                    "message_id": message_id,
                    "content": content,
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
                    content=content,
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
        if _is_team_discussion_segment(debate) and not _is_task_assign_segment(debate.segment_label):
            return await self._team_discussion_generate(state)
        if state.get("rewrite_count", 0) >= 1:
            state["reflection_polished"] = None

        polished: str | None = state.get("reflection_polished")
        use_reflection_output = bool(polished)

        if use_reflection_output:
            self._mark(debate, "speech_generate", "播送反思后的定稿发言。")
        else:
            self._mark(debate, "speech_generate", "DeepSeek 正在流式生成 Markdown 发言。")
        agent = self._active_agent(debate)
        messages, sources = self._speech_messages(debate, state, agent)
        model = resolve_model(phase=debate.phase, speaker_id=agent.id)
        message_id = str(uuid4())
        content = ""
        raw_content = ""

        if agent.side == "judge" and "输出裁判报告" in (debate.segment_label or ""):
            self._mark(debate, "speech_generate", "裁判正在生成终局报告。")
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
        self._mark(debate, "fact_check", "快速检查发言是否含明显无来源断言。")
        messages: list[DebateMessage] = state.get("draft_messages") or [state["draft_message"]]
        risky_terms = ("研究表明", "数据显示", "%", "法律规定", "论文指出")
        facts_ok = True
        for message in messages:
            message.content = strip_model_reasoning(sanitize_citations(message.content, message.sources))
            unverified = has_unverified_citations(message.content, message.sources)
            risky = any(term in message.content for term in risky_terms)
            if unverified or (risky and not message.sources):
                facts_ok = False
            # 设置幻觉风险等级供前端展示
            import re as _re
            has_sources = bool(message.sources)
            has_numbers = bool(_re.search(r'\d+[\.\d]*\s*%|\d{4}\s*年|\d+\s*(万|亿|项|人|次)', message.content))
            if unverified or (risky and not has_sources):
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
        self._mark(debate, "publish_message", "写入长期记录并准备实时广播。")
        messages: list[DebateMessage] = state.get("draft_messages") or [state["draft_message"]]
        for message in messages:
            if message is not None:
                debate.messages.append(message)
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
        self._mark(debate, "judge_score", "裁判按逻辑、回应和证据进行快速评分。")
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
        self._mark(debate, "turn_router", "按 4v4 标准赛制进入下一环节。")
        debate.turn_index += 1
        advance_schedule(debate)
        debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)
        return state


debate_graph = DebateGraph()
