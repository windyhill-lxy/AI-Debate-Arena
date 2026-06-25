from datetime import datetime

from app.core.time_utils import utc_now
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DebateVisibility(str, Enum):
    context = "context"
    realistic = "realistic"
    god = "god"
    all_visible = "all_visible"
    own_side_only = "own_side_only"


class DebateTiming(str, Enum):
    limited = "limited"
    unlimited = "unlimited"


class DebateMode(str, Enum):
    ai_autonomous = "ai_autonomous"
    user_affirmative = "user_affirmative"
    user_negative = "user_negative"
    online_match = "online_match"


class AgentRole(BaseModel):
    id: str
    name: str
    side: Literal["affirmative", "negative", "judge", "assistant"]
    position: int = 0  # 1-4 辩手位，0 表示裁判/系统角色
    avatar: str
    model: str
    persona: str
    visible: bool = True


class Source(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    excerpt: str
    url: str | None = None
    reliability: float = Field(default=0.8, ge=0, le=1)


class ArgumentBankItem(BaseModel):
    id: str
    side: Literal["affirmative", "negative"]
    title: str = ""
    claim: str
    source: str = ""
    locked: bool = True


class DebateMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    debate_id: str
    speaker_id: str
    speaker_name: str
    side: str
    content: str
    phase: str
    segment_label: str | None = None
    sources: list[Source] = Field(default_factory=list)
    private_thought: str | None = None
    strategy: str | None = None
    audio_url: str | None = None
    audio_urls: list[str] = Field(default_factory=list)
    tts_voice: str | None = None
    tts_instructions: str | None = None
    score_delta: float | None = None
    score_reason: str | None = None
    speech_flag: Literal["ok", "inappropriate"] | None = None
    review_reason: str | None = None
    hallucination_risk: Literal["low", "medium", "high"] | None = None
    created_at: datetime = Field(default_factory=utc_now)


class WorkflowNode(BaseModel):
    id: str
    label: str
    kind: Literal["input", "retrieval", "llm", "check", "action", "judge", "router"]
    status: Literal["pending", "running", "done", "blocked"] = "pending"
    detail: str = ""
    stage: str = ""
    lane: int = 0


class ScheduleItem(BaseModel):
    index: int
    id: str
    label: str
    phase: str
    seconds: int
    section: str
    status: Literal["pending", "current", "done"] = "pending"


class MaterialInput(BaseModel):
    title: str = "辩题参考资料"
    content: str = ""


class OnlineParticipant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = "联机辩手"
    side: Literal["affirmative", "negative", "spectator"] = "spectator"
    position: int = Field(default=0, ge=0, le=4)
    connected: bool = True
    last_ip: str | None = None
    joined_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ParticipantJoin(BaseModel):
    participant_id: str | None = None
    name: str = "联机辩手"
    side: Literal["affirmative", "negative", "spectator"] = "spectator"
    position: int = Field(default=0, ge=0, le=4)


class DebateCreate(BaseModel):
    topic: str = "人工智能是否会提升青少年的综合学习能力"
    mode: DebateMode = DebateMode.ai_autonomous
    user_side: Literal["affirmative", "negative"] | None = None
    user_position: int = Field(default=1, ge=1, le=4)
    user_name: str = "用户辩手"
    visibility: DebateVisibility = DebateVisibility.context
    timing: DebateTiming = DebateTiming.limited
    turn_seconds: int = 90
    tts_enabled: bool = True
    human_timeout_penalty_enabled: bool = True
    format: Literal["formal", "free"] = "formal"
    schedule_template: str = "formal_4v4"
    materials: list[MaterialInput] = Field(default_factory=list)
    session_id: str | None = None
    opening_evidence_prep_id: str | None = None
    models: dict[str, str] = Field(default_factory=dict)


class MaterialUpload(BaseModel):
    title: str = "辩题参考资料"
    content: str
    replace: bool = False


class DebateImport(BaseModel):
    filename: str = "debate-history.md"
    content: str


class UserMessageCreate(BaseModel):
    speaker_id: str = "user"
    speaker_name: str = "用户辩手"
    side: Literal["affirmative", "negative"] = "affirmative"
    position: int = 1
    content: str
    participant_id: str | None = None


class AssistRequest(BaseModel):
    side: Literal["affirmative", "negative"] = "affirmative"
    position: int = 1
    draft: str = ""


class OpeningTrainingAnalyze(BaseModel):
    topic: str
    side: Literal["affirmative", "negative"] = "affirmative"
    draft: str


class OpeningTrainingAutoImprove(BaseModel):
    topic: str
    side: Literal["affirmative", "negative"] = "affirmative"
    max_rounds: int = Field(default=6, ge=1, le=12)


class OpeningTrainingPolish(BaseModel):
    topic: str
    side: Literal["affirmative", "negative"] = "affirmative"
    draft: str
    advice: list[str] = Field(default_factory=list)


class UserDraftUpdate(BaseModel):
    draft: str = ""


class DebateState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    mode: DebateMode = DebateMode.ai_autonomous
    visibility: DebateVisibility
    timing: DebateTiming
    turn_seconds: int
    format: str
    awaiting_user: bool = False
    auto_running: bool = False
    phase: str = "pre_match"
    schedule_index: int = 0
    segment_label: str = "赛前介绍"
    segment_rules: str = ""
    segment_seconds: int = 60
    turn_index: int = 0
    active_speaker_id: str = "judge"
    user_side: Literal["affirmative", "negative"] | None = None
    user_position: int = Field(default=1, ge=1, le=4)
    user_name: str = "用户辩手"
    agents: list[AgentRole]
    messages: list[DebateMessage] = Field(default_factory=list)
    workflow: list[WorkflowNode] = Field(default_factory=list)
    schedule: list[ScheduleItem] = Field(default_factory=list)
    score: dict[str, float] = Field(default_factory=lambda: {"affirmative": 0, "negative": 0})
    match_summary: str = ""
    schedule_template: str = "formal_4v4"
    user_draft: str = ""
    tts_enabled: bool = True
    visibility_locked: bool = False
    timing_locked: bool = False
    rules_locked_at: datetime | None = None
    human_timeout_penalty_enabled: bool = True
    timeout_penalty_points: float = 0.5
    awaiting_user_since: datetime | None = None
    timeout_penalty_applied_segments: list[str] = Field(default_factory=list)
    participants: list[OnlineParticipant] = Field(default_factory=list)
    online_ready: bool = False
    materials_preview: list[MaterialInput] = Field(default_factory=list)
    argument_bank: dict[str, list[ArgumentBankItem]] = Field(
        default_factory=lambda: {"affirmative": [], "negative": []}
    )
    argument_bank_locked: bool = False
    opening_evidence_completed: bool = False
    online_session_id: str | None = None
    free_aff_remaining_sec: int = 240
    free_neg_remaining_sec: int = 240
    free_turn_counter: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def default_agents() -> list[AgentRole]:
    pro = "deepseek-v4-flash"
    return [
        AgentRole(
            id="aff_1",
            name="云汐",
            side="affirmative",
            position=1,
            avatar="/src/assets/agents/agent-silver.png",
            model=pro,
            persona="正方一辩：立论框架手，擅长定义辩题与搭建论证体系。",
        ),
        AgentRole(
            id="aff_2",
            name="澜汐",
            side="affirmative",
            position=2,
            avatar="/src/assets/agents/agent-blue.png",
            model=pro,
            persona="正方二辩：驳论与对辩核心，逻辑拆解与短兵相接。",
        ),
        AgentRole(
            id="aff_3",
            name="珂绫",
            side="affirmative",
            position=3,
            avatar="/src/assets/agents/agent-k.png",
            model=pro,
            persona="正方三辩：质辩提问与质辩小结，善于设计问题并总结对方回答漏洞。",
        ),
        AgentRole(
            id="aff_4",
            name="青萝",
            side="affirmative",
            position=4,
            avatar="/src/assets/agents/agent-green.png",
            model=pro,
            persona="正方四辩：质辩应答与总结陈词，收束全场、升华价值。",
        ),
        AgentRole(
            id="neg_1",
            name="橙律",
            side="negative",
            position=1,
            avatar="/src/assets/agents/agent-orange.png",
            model=pro,
            persona="反方一辩：立论框架手，强调风险、边界与替代标准。",
        ),
        AgentRole(
            id="neg_2",
            name="星白",
            side="negative",
            position=2,
            avatar="/src/assets/agents/agent-white.png",
            model=pro,
            persona="反方二辩：驳论与对辩，擅长类比与框架置换。",
        ),
        AgentRole(
            id="neg_3",
            name="凛Z",
            side="negative",
            position=3,
            avatar="/src/assets/agents/agent-z.png",
            model=pro,
            persona="反方三辩：质辩提问与质辩小结，质询犀利、战场梳理清晰。",
        ),
        AgentRole(
            id="neg_4",
            name="浅笑",
            side="negative",
            position=4,
            avatar="/src/assets/agents/agent-sweat.png",
            model=pro,
            persona="反方四辩：质辩应答与总结陈词，先声夺人、终局收束。",
        ),
        AgentRole(
            id="judge",
            name="紫苑裁判",
            side="judge",
            position=0,
            avatar="/src/assets/agents/agent-purple.png",
            model=pro,
            persona="主席/裁判：维持秩序、评议胜负、点评双方。",
        ),
    ]


def build_schedule_status(current_index: int, template: str = "formal_4v4") -> list[ScheduleItem]:
    from app.services.schedule_config import load_schedule

    formal = load_schedule(template)
    items: list[ScheduleItem] = []
    finished = current_index >= len(formal)
    for i, seg in enumerate(formal):
        if finished or i < current_index:
            status = "done"
        elif i == current_index:
            status = "current"
        else:
            status = "pending"
        items.append(
            ScheduleItem(
                index=i,
                id=seg.id,
                label=seg.label,
                phase=seg.phase,
                seconds=seg.seconds,
                section=seg.section,
                status=status,
            )
        )
    return items


def workflow_template() -> list[WorkflowNode]:
    nodes = [
        ("topic_parse", "辩题解析", "input", "抽取概念、争点、评价标准。", "赛前准备", 1),
        ("stance_assign", "确定持方", "action", "锁定正反方立场与胜负标准。", "赛前准备", 2),
        ("role_confirm", "组内角色确认", "action", "确认一至四辩与裁判职责。", "赛前准备", 3),
        ("opening_evidence_bank", "AI 检索真实论据入库", "retrieval", "按正反方分别检索真实案例、数据、报告并入库。", "立论前准备", 1),
        ("opening_task_assign", "一辩任务分配", "action", "一辩基于论据库拆解立论框架与队友任务。", "立论前准备", 2),
        ("task_reason_check", "大模型判断任务合理性", "router", "检查分工是否覆盖定义、标准、论据。", "立论前准备", 3),
        ("point_split_confirm", "论点分工确认", "action", "确认每位辩手负责的论点。", "立论前准备", 4),
        ("evidence_split_confirm", "论据分配确认", "action", "确认每个论点需要的事实类型。", "立论前准备", 5),
        ("team_opening_discussion", "队内讨论(立论)", "llm", "组内研究如何使用本方论据库。", "立论前准备", 6),
        ("opening_strategy_lock", "立论策略锁定", "action", "锁定开篇标准与表达节奏。", "立论前准备", 7),
        ("rag_retrieve", "RAG 检索:增强论点", "retrieval", "为当前发言检索可引用资料。", "立论/驳论/总结", 1),
        ("strategy_plan", "策略规划", "llm", "按当前环节生成攻防路线。", "立论/驳论/总结", 2),
        ("stance_decision", "大模型判断发言方向", "router", "结合环节和历史选择发言任务。", "立论/驳论/总结", 3),
        (
            "reflection_draft_finalize",
            "反思:草稿→定稿",
            "llm",
            "非自由辩时一轮内部草稿再凝练为正式发言。",
            "立论/驳论/总结",
            4,
        ),
        ("speech_generate", "辩手发言生成", "llm", "DeepSeek Flash 流式生成 Markdown 发言。", "立论/驳论/总结", 5),
        ("fact_check", "RAG 检索:事实核查", "check", "核对引用、数字、法规和来源。", "立论/驳论/总结", 6),
        ("argument_strength_check", "大模型判断论点强度", "judge", "评估论点强度、回应性和漏洞。", "立论/驳论/总结", 7),
        ("rebuttal_effect_check", "大模型判断驳论有效性", "judge", "判断反驳是否命中对方核心。", "立论/驳论/总结", 8),
        ("free_timer_pause", "暂停计时", "action", "自由辩论前暂停并汇总战场。", "自由辩论前准备", 1),
        ("rag_opponent_predict", "RAG 检索:对方论点预测", "retrieval", "预测对手下一轮可能推进的论点。", "自由辩论前准备", 2),
        ("attack_defense_adjust", "攻防策略调整", "action", "选择主攻点、防守底线和接力顺序。", "自由辩论前准备", 4),
        ("rag_attack_cases", "RAG 检索:攻防案例库", "retrieval", "检索短句可用案例。", "自由辩论前准备", 5),
        ("free_strategy_check", "大模型判断策略可行性", "router", "判断是否能进入自由辩论。", "自由辩论前准备", 6),
        ("temporary_roles", "角色临时分工", "action", "确认谁主攻、谁补证、谁收束。", "自由辩论前准备", 7),
        ("free_ready", "准备就绪", "action", "自由辩论开始。", "自由辩论前准备", 8),
        ("free_alternate_output", "直接交替输出", "llm", "双方短句交替、快速回应。", "自由辩论环节", 1),
        ("rag_realtime_rebuttal", "RAG 检索:实时反驳", "retrieval", "为下一句反击检索事实支撑。", "自由辩论环节", 2),
        ("free_continue_check", "大模型判断是否继续", "router", "根据剩余轮次与战场热度判断继续。", "自由辩论环节", 3),
        ("free_end", "结束自由辩论", "action", "进入总结陈词准备。", "自由辩论环节", 4),
        ("closing_receive_summary", "四辩接收汇总", "action", "四辩接收全场攻防摘要。", "总结陈词前准备", 1),
        ("rag_full_knowledge", "RAG 检索:全场知识点", "retrieval", "汇总可引用事实和战场记录。", "总结陈词前准备", 2),
        ("closing_frame_confirm", "总结框架确认", "action", "锁定四辩总结结构。", "总结陈词前准备", 4),
        ("rag_closing_template", "RAG 检索:总结范本", "retrieval", "检索总结陈词结构范本。", "总结陈词环节", 1),
        ("closing_quality_check", "大模型判断总结质量", "judge", "检查总结是否覆盖全场交锋。", "总结陈词环节", 2),
        ("score_summary", "汇总全程得分", "judge", "汇总每轮逻辑、证据、表达得分。", "裁判最终裁决", 1),
        ("rag_judge_criteria", "RAG 检索:裁判准则库", "retrieval", "检索评分规则和扣分标准。", "裁判最终裁决", 2),
        ("judge_comment_generate", "大模型评语生成", "llm", "生成双方评语与最佳辩手候选。", "裁判最终裁决", 3),
        ("winner_decision", "判定胜负", "router", "结合得分与关键战场判定胜负。", "裁判最终裁决", 4),
        ("final_verdict", "输出裁判报告", "judge", "输出胜负、理由、得分和改进建议。", "裁判最终裁决", 5),
        ("publish_message", "发布与广播", "action", "写入 MongoDB，并通过 Redis/WebSocket 推送。", "系统执行", 1),
        ("judge_score", "裁判评分", "judge", "评价逻辑、证据、表达与幻觉风险。", "系统执行", 2),
        ("turn_router", "赛制环节推进", "router", "按精细赛程进入下一节点。", "系统执行", 3),
    ]
    return [
        WorkflowNode(id=id_, label=label, kind=kind, detail=detail, stage=stage, lane=lane)
        for id_, label, kind, detail, stage, lane in nodes
    ]
