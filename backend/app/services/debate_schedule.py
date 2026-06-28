from dataclasses import dataclass
from typing import Literal

from app.models import DebateState


@dataclass(frozen=True)
class DebateSegment:
    id: str
    phase: str
    label: str
    rules: str
    seconds: int
    speaker_side: Literal["affirmative", "negative", "judge", "assistant"]
    speaker_position: int  # 1-4 for debaters, 0 for judge
    section: str  # pre | main | post


def agent_id(side: str, position: int) -> str:
    if side in {"judge", "assistant"}:
        return side
    prefix = "aff" if side == "affirmative" else "neg"
    return f"{prefix}_{position}"


def seg(
    id: str,
    phase: str,
    label: str,
    rules: str,
    seconds: int,
    side: Literal["affirmative", "negative", "judge", "assistant"],
    position: int = 0,
    section: str = "main",
) -> DebateSegment:
    return DebateSegment(id, phase, label, rules, seconds, side, position, section)


# 精细化 4v4 智能体赛程：把准备、RAG、LLM 判断、发言与裁判裁决都显式展示。
FORMAL_SCHEDULE: list[DebateSegment] = [
    seg(
        "pre_match_opening",
        "pre_match",
        "赛前准备 · 主持开场",
        "仅一次主持：简短欢迎→辩题争点与胜负标准→正反持方与一至四辩分工→宣布进入立论前准备；勿重复欢迎辞或全文复述辩题。",
        90,
        "judge",
        section="pre",
    ),
    seg("opening_evidence_bank", "opening_prep", "立论前准备 · AI检索真实论据入库", "按正反方分别检索真实事实、案例、数据和报告，只把可核验论据写入论据库。", 45, "judge", section="pre"),
    seg("opening_task_assign", "opening_prep", "立论前准备 · 一辩任务分配", "一辩向队友分配定义、论点、论据和风险回应任务。", 45, "affirmative", 1, "pre"),
    seg("neg_opening_task_assign", "opening_prep", "立论前准备 · 反方一辩任务分配", "反方一辩向队友分配定义、论点、论据和风险回应任务。", 45, "negative", 1, "pre"),
    seg("opening_task_check", "opening_prep", "立论前准备 · 大模型判断:任务合理性", "检查任务是否覆盖定义、论证链、证据和反方可能攻击点。", 30, "judge", section="pre"),
    seg("point_split", "opening_prep", "立论前准备 · 论点分工确认", "确认各辩手负责的主论点和攻防位置。", 30, "judge", section="pre"),
    seg("evidence_split", "opening_prep", "立论前准备 · 论据分配确认", "确认每个论点对应的事实、案例和可验证来源。", 30, "judge", section="pre"),
    seg("aff_opening_discussion", "opening_prep", "立论前准备 · 正方队内讨论(立论)", "正方队内研究如何使用本方论据库并规划立论策略。", 45, "affirmative", 1, "pre"),
    seg("neg_opening_discussion", "opening_prep", "立论前准备 · 反方队内讨论(立论)", "反方队内研究如何使用本方论据库并规划立论策略。", 45, "negative", 1, "pre"),
    seg("opening_strategy_lock", "opening_prep", "立论前准备 · 立论策略锁定", "锁定开篇标准、核心论点和表达节奏。", 30, "judge", section="pre"),
    seg("aff_opening_1", "opening_statement", "正方一辩立论", "定义辩题、提出分论点，搭建正方论证框架。", 180, "affirmative", 1),
    seg("aff_opening_rag", "argument_review", "立论环节 · RAG检索:增强论点", "围绕正方立论检索增强论据和潜在漏洞。", 25, "judge"),
    seg("aff_opening_strength", "argument_review", "立论环节 · 大模型判断:论点强度", "判断正方论点强度、证据充分性和可攻击点。", 25, "judge"),
    seg("neg_opening_1", "opening_statement", "反方一辩立论", "定义辩题、提出分论点，搭建反方论证框架。", 180, "negative", 1),
    seg("neg_opening_rag", "argument_review", "立论环节 · RAG检索:增强论点", "围绕反方立论检索增强论据和潜在漏洞。", 25, "judge"),
    seg("neg_opening_strength", "argument_review", "立论环节 · 大模型判断:论点强度", "判断反方论点强度、证据充分性和可攻击点。", 25, "judge"),
    seg("neg_rebuttal_2", "rebuttal", "驳立论 · 反方二辩", "反方二辩针对正方一辩立论进行反驳与补充；无质询、无问答。", 120, "negative", 2),
    seg("neg_rebuttal_rag", "rebuttal_review", "驳论环节 · RAG检索:反驳论据", "围绕反方二辩驳论检索可核验反驳依据和潜在风险。", 25, "judge"),
    seg("neg_rebuttal_quality", "rebuttal_review", "驳论环节 · 大模型判断:驳论有效性", "判断反方二辩是否命中正方一辩立论漏洞并补强本方立场。", 25, "judge"),
    seg("aff_rebuttal_2", "rebuttal", "驳立论 · 正方二辩", "正方二辩针对反方一辩立论进行反驳与补充；无质询、无问答。", 120, "affirmative", 2),
    seg("aff_rebuttal_rag", "rebuttal_review", "驳论环节 · RAG检索:反驳论据", "围绕正方二辩驳论检索可核验反驳依据和潜在风险。", 25, "judge"),
    seg("aff_rebuttal_quality", "rebuttal_review", "驳论环节 · 大模型判断:驳论有效性", "判断正方二辩是否命中反方一辩立论漏洞并补强本方立场。", 25, "judge"),
    seg("aff_cross_q_neg1", "cross_examination", "质辩 · 正方三辩问反方一辩", "提问方：正方三辩；回答方：反方一辩。正方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "affirmative", 3),
    seg("neg1_cross_answer", "cross_examination", "质辩 · 反方一辩回答", "提问方：正方三辩；回答方：反方一辩。反方一辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "negative", 1),
    seg("aff_cross_q_neg2", "cross_examination", "质辩 · 正方三辩问反方二辩", "提问方：正方三辩；回答方：反方二辩。正方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "affirmative", 3),
    seg("neg2_cross_answer", "cross_examination", "质辩 · 反方二辩回答", "提问方：正方三辩；回答方：反方二辩。反方二辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "negative", 2),
    seg("aff_cross_q_neg4", "cross_examination", "质辩 · 正方三辩问反方四辩", "提问方：正方三辩；回答方：反方四辩。正方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "affirmative", 3),
    seg("neg4_cross_answer", "cross_examination", "质辩 · 反方四辩回答", "提问方：正方三辩；回答方：反方四辩。反方四辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "negative", 4),
    seg("neg_cross_q_aff1", "cross_examination", "质辩 · 反方三辩问正方一辩", "提问方：反方三辩；回答方：正方一辩。反方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "negative", 3),
    seg("aff1_cross_answer", "cross_examination", "质辩 · 正方一辩回答", "提问方：反方三辩；回答方：正方一辩。正方一辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "affirmative", 1),
    seg("neg_cross_q_aff2", "cross_examination", "质辩 · 反方三辩问正方二辩", "提问方：反方三辩；回答方：正方二辩。反方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "negative", 3),
    seg("aff2_cross_answer", "cross_examination", "质辩 · 正方二辩回答", "提问方：反方三辩；回答方：正方二辩。正方二辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "affirmative", 2),
    seg("neg_cross_q_aff4", "cross_examination", "质辩 · 反方三辩问正方四辩", "提问方：反方三辩；回答方：正方四辩。反方三辩只提出一个问题，提问不得超过15秒，问题必须清晰规范，不得自答。", 15, "negative", 3),
    seg("aff4_cross_answer", "cross_examination", "质辩 · 正方四辩回答", "提问方：反方三辩；回答方：正方四辩。正方四辩针对上一问直接作答，不得闪躲或反问；本组回答累计90秒，本次控制在30秒内。", 30, "affirmative", 4),
    seg("aff_summary_3", "segment_summary", "质辩小结 · 正方三辩", "正方三辩针对质辩问答进行小结，梳理对方回答漏洞并巩固己方立场；无问答。", 90, "affirmative", 3),
    seg("aff_summary_fact", "argument_review", "质辩环节 · RAG检索:事实核查", "核查正方小结中的事实和引用风险。", 25, "judge"),
    seg("neg_summary_3", "segment_summary", "质辩小结 · 反方三辩", "反方三辩针对质辩问答进行小结，拆解正方回答漏洞并巩固己方立场；无问答。", 90, "negative", 3),
    seg("neg_summary_fact", "argument_review", "质辩环节 · RAG检索:事实核查", "核查反方小结中的事实和引用风险。", 25, "judge"),
    seg("free_pause", "free_prep", "自由辩论前准备 · 暂停计时", "暂停计时并汇总双方当前战场。", 20, "judge"),
    seg("free_predict_rag", "free_prep", "自由辩论前准备 · RAG检索:对方论点预测", "预测对方自由辩论可能主攻方向。", 30, "judge"),
    seg("free_strategy_adjust", "free_prep", "自由辩论前准备 · 攻防策略调整", "确定主攻点、防守底线和换位节奏。", 30, "judge"),
    seg("free_case_rag", "free_prep", "自由辩论前准备 · RAG检索:攻防案例库", "检索自由辩论可快速引用的案例。", 30, "judge"),
    seg("free_strategy_check", "free_prep", "自由辩论前准备 · 大模型判断:策略可行性", "判断策略是否可执行、是否存在明显证据漏洞。", 25, "judge"),
    seg("free_temp_roles", "free_prep", "自由辩论前准备 · 角色临时分工", "确认谁主攻、谁补证、谁收束。", 25, "judge"),
    seg("free_ready", "free_prep", "自由辩论前准备 · 准备就绪", "宣布进入直接交替输出。", 15, "judge"),
    seg(
        "free_debate_pool",
        "free_debate",
        "自由辩论 · 双方各4分钟",
        "正方先发言后交替；每次只说一句话；一方落座后暂停本方计时，另一方继续。",
        30,
        "affirmative",
        1,
    ),
    seg("free_realtime_rag", "free_review", "自由辩论环节 · RAG检索:实时反驳", "汇总自由辩论中可继续追打的事实点。", 25, "judge"),
    seg("free_continue_check", "free_review", "自由辩论环节 · 大模型判断:是否继续", "根据战场热度、剩余轮次和重复度判断结束。", 25, "judge"),
    seg("free_end", "free_review", "自由辩论环节 · 结束自由辩论", "裁判宣布自由辩论结束，进入总结准备。", 15, "judge"),
    seg("closing_receive", "closing_prep", "总结陈词前准备 · 四辩接收汇总", "四辩接收全场论点、漏洞和得分摘要。", 35, "judge"),
    seg("closing_knowledge_rag", "closing_prep", "总结陈词前准备 · RAG检索:全场知识点", "汇总全场可验证事实和关键交锋。", 30, "judge"),
    seg("closing_frame", "closing_prep", "总结陈词前准备 · 总结框架确认", "锁定四辩总结结构：回应、比较、升华。", 25, "judge"),
    seg("closing_neg4", "closing", "反方四辩总结", "升华主题，梳理全场交锋，重申反方胜负标准。", 180, "negative", 4),
    seg("closing_neg_rag", "closing_review", "总结陈词环节 · RAG检索:总结范本", "检索反方总结结构范本和表达模板。", 25, "judge"),
    seg("closing_neg_quality", "closing_review", "总结陈词环节 · 大模型判断:总结质量", "判断反方总结是否覆盖关键战场。", 25, "judge"),
    seg("closing_aff4", "closing", "正方四辩总结", "升华主题，梳理全场交锋，重申正方胜负标准。", 180, "affirmative", 4),
    seg("closing_aff_rag", "closing_review", "总结陈词环节 · RAG检索:总结范本", "检索正方总结结构范本和表达模板。", 25, "judge"),
    seg("closing_aff_quality", "closing_review", "总结陈词环节 · 大模型判断:总结质量", "判断正方总结是否覆盖关键战场。", 25, "judge"),
    seg("score_summary", "post_match", "裁判最终裁决 · 汇总全程得分", "汇总双方每轮逻辑、证据、表达与幻觉扣分。", 35, "judge", section="post"),
    seg("judge_criteria_rag", "post_match", "裁判最终裁决 · RAG检索:裁判准则库", "检索评分准则、扣分规则和最佳辩手标准。", 30, "judge", section="post"),
    seg("judge_comment", "post_match", "裁判最终裁决 · 大模型评语生成", "生成双方表现评语和关键战场复盘。", 45, "judge", section="post"),
    seg("winner_decision", "post_match", "裁判最终裁决 · 判定胜负", "结合得分与战场控制力判定胜负。", 35, "judge", section="post"),
    seg("post_verdict", "post_match", "裁判最终裁决 · 输出裁判报告", "输出胜负、分项得分、最佳辩手和改进建议。", 120, "judge", section="post"),
]


def _schedule_for(debate: DebateState) -> list[DebateSegment]:
    from app.services.schedule_config import load_schedule

    template = getattr(debate, "schedule_template", None) or "formal_4v4"
    return load_schedule(template)


def get_segment(debate: DebateState, index: int) -> DebateSegment | None:
    schedule = _schedule_for(debate)
    if 0 <= index < len(schedule):
        return schedule[index]
    return None


def _should_skip_segment(debate: DebateState, segment: DebateSegment) -> bool:
    label = segment.label or ""
    if not getattr(debate, "team_discussion_enabled", False):
        team_setup_ids = {
            "opening_task_assign",
            "neg_opening_task_assign",
            "opening_task_check",
            "point_split",
            "evidence_split",
            "aff_opening_discussion",
            "neg_opening_discussion",
            "opening_strategy_lock",
        }
        if segment.id in team_setup_ids or "队内讨论" in label:
            return True
    if getattr(debate, "rag_review_mode", "essential") != "full":
        review_phases = {"argument_review", "rebuttal_review", "free_review", "closing_review"}
        if segment.phase in review_phases:
            return True
        if segment.id in {"free_predict_rag", "free_case_rag", "closing_knowledge_rag", "judge_criteria_rag"}:
            return True
        if "RAG检索" in label and segment.id != "opening_evidence_bank":
            return True
        if "大模型判断" in label and segment.phase != "post_match":
            return True
    return False


def apply_segment(debate: DebateState, index: int) -> None:
    schedule = _schedule_for(debate)
    while 0 <= index < len(schedule) and _should_skip_segment(debate, schedule[index]):
        index += 1
    segment = schedule[index] if 0 <= index < len(schedule) else None
    if segment is None:
        debate.phase = "finished"
        debate.segment_label = "比赛结束"
        debate.segment_rules = "等待评委宣布结果。"
        debate.segment_seconds = 0
        debate.active_speaker_id = "judge"
        return

    debate.schedule_index = index
    debate.phase = segment.phase
    debate.segment_label = segment.label
    debate.segment_rules = segment.rules
    debate.segment_seconds = segment.seconds
    debate.turn_seconds = segment.seconds

    debate.active_speaker_id = agent_id(segment.speaker_side, segment.speaker_position)


def _free_debate_exit_index(schedule: list[DebateSegment]) -> int:
    for i, segment in enumerate(schedule):
        if segment.phase == "free_review":
            return i
    return len(schedule)


def _side_from_speaker_id(speaker_id: str) -> Literal["affirmative", "negative"] | None:
    if speaker_id.startswith("aff_"):
        return "affirmative"
    if speaker_id.startswith("neg_"):
        return "negative"
    return None


def _advance_free_debate_pool(debate: DebateState, schedule: list[DebateSegment]) -> bool:
    current = get_segment(debate, debate.schedule_index)
    if current is None or current.phase != "free_debate":
        return False

    # schedule_index stays on free_debate_pool; use active speaker for the side that just spoke.
    last_side = _side_from_speaker_id(debate.active_speaker_id) or current.speaker_side

    spent = max(1, min(current.seconds, debate.segment_seconds or current.seconds))
    if last_side == "affirmative":
        debate.free_aff_remaining_sec = max(0, debate.free_aff_remaining_sec - spent)
    elif last_side == "negative":
        debate.free_neg_remaining_sec = max(0, debate.free_neg_remaining_sec - spent)

    debate.free_turn_counter += 1
    if debate.free_aff_remaining_sec <= 0 and debate.free_neg_remaining_sec <= 0:
        apply_segment(debate, _free_debate_exit_index(schedule))
        return True
    next_side = "negative" if last_side == "affirmative" else "affirmative"
    if next_side == "affirmative" and debate.free_aff_remaining_sec <= 0:
        next_side = "negative"
    if next_side == "negative" and debate.free_neg_remaining_sec <= 0:
        next_side = "affirmative"
    if debate.free_aff_remaining_sec <= 0 and debate.free_neg_remaining_sec <= 0:
        apply_segment(debate, _free_debate_exit_index(schedule))
        return True

    position = ((debate.free_turn_counter - 1) % 4) + 1
    side_label = "正方" if next_side == "affirmative" else "反方"
    remaining = debate.free_aff_remaining_sec if next_side == "affirmative" else debate.free_neg_remaining_sec
    debate.phase = "free_debate"
    debate.segment_label = f"自由辩论 · {side_label} · 队时剩余 {remaining}s"
    debate.segment_rules = current.rules
    debate.segment_seconds = current.seconds
    debate.turn_seconds = current.seconds
    debate.active_speaker_id = agent_id(next_side, position)
    return True


def advance_schedule(debate: DebateState) -> bool:
    """推进到下一环节，返回是否还有下一环节。"""
    schedule = _schedule_for(debate)
    current = get_segment(debate, debate.schedule_index)
    if current and current.phase == "free_debate":
        return _advance_free_debate_pool(debate, schedule)

    next_index = debate.schedule_index + 1
    if next_index >= len(schedule):
        apply_segment(debate, len(schedule))  # finished state
        return False
    apply_segment(debate, next_index)
    if get_segment(debate, debate.schedule_index) and get_segment(debate, debate.schedule_index).phase == "free_debate":
        debate.free_aff_remaining_sec = 240
        debate.free_neg_remaining_sec = 240
        debate.free_turn_counter = 0
    return True


def init_schedule(debate: DebateState) -> None:
    apply_segment(debate, 0)


def is_free_debate_phase(debate: DebateState) -> bool:
    return debate.phase == "free_debate"


_DEFAULT_HINTS: dict[str, str] = {
        "opening_prep": "这是立论前准备：以内部会议口吻明确任务、论点和证据分配，输出要简洁；安排好三个论点的分工（谁主讲哪个论点）。",
        "opening_statement": (
            "这是开篇立论：必须包含三个明确论点，每个论点附一条具体论据（真实事例或研究数据，非常识性推断）；"
            "发言总字数控制在 800 到 1000 个汉字，结构为：定义→论点一→论点二→论点三→价值升华。"
        ),
        "argument_review": "这是立论后的检索与判断：用裁判口吻评估论点强度与证据缺口，不给任何一方战术指导。",
        "rebuttal": (
            "这是驳论：先抓住对方立论中最明显的逻辑漏洞（因果谬误/偷换概念/以偏概全）予以反驳，"
            "再用具体事例巩固己方论点；控制在3-5句，直击核心。"
        ),
        "rebuttal_review": "这是驳论后的检索与判断：评价反驳是否命中核心，只做中立判定。",
        "cross_examination": "这是质辩：三辩每次只向指定辩手提出一个问题；回答方只回答上一问，不得反问或闪躲。",
        "segment_summary": "这是质辩小结：由三辩梳理本场质辩得失，指出对方回答中的核心漏洞；控制在4-6句，不要重复已说内容。",
        "free_prep": "这是自由辩论前准备：预测对方论点，安排短句攻防和临时分工（谁主攻/谁举例/谁守防）。",
        "free_debate": (
            "这是自由辩论：极短句、快节奏、团队配合，每次只讲一句话。"
            "优先指出对方最明显的逻辑错误（因果谬误、偷换概念、以偏概全、举例失当）；"
            "若无明显逻辑漏洞，再提出己方新论点或数据支撑。"
        ),
        "free_review": "这是自由辩论复盘：判断是否继续，并为总结陈词收束战场。",
        "closing_prep": "这是总结陈词前准备：汇总全场知识点、攻防记录和总结框架；确认三个论点是否均已充分论证。",
        "closing": "这是总结陈词：全面回顾、升华价值、回应全场未解问题；须覆盖全部论点和框架，不得遗漏。",
        "closing_review": "这是总结质量判断：检查总结是否回应全场关键争点，是否覆盖三个论点。",
        "pre_match": "主持开场（全场仅一次）：欢迎→辩题争点→胜负标准→正反分工→下一环节；禁止重复历史主持辞。",
        "post_match": "赛后裁决：汇总得分、检索裁判准则、宣布胜负并输出报告。",
}


def segment_prompt_hint(debate: DebateState) -> str:
    from app.core.custom_prompts import get_phase_hint_override
    segment = get_segment(debate, debate.schedule_index)
    if not segment:
        return ""
    override = get_phase_hint_override(segment.phase)
    if override:
        return override
    return _DEFAULT_HINTS.get(segment.phase, segment.rules)


def schedule_overview(template: str = "formal_4v4") -> list[dict]:
    from app.services.schedule_config import load_schedule

    schedule = load_schedule(template)
    return [
        {
            "index": i,
            "id": s.id,
            "label": s.label,
            "phase": s.phase,
            "seconds": s.seconds,
            "section": s.section,
        }
        for i, s in enumerate(schedule)
    ]
