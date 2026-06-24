from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.models import AgentRole, DebateState, Source
from app.services.ai_context_manager import build_ai_debater_context, format_argument_bank
from app.services.argument_bank import argument_ids_for_side, referenced_argument_ids
from app.services.debate_mode import debate_user_position, debate_user_side
from app.services.debate_schedule import segment_prompt_hint
from app.services.llm import DeepSeekError, chat_completion, resolve_model, strip_model_reasoning

ChatCompletionFn = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class TeamDiscussionContext:
    stance_action: str = "队内讨论"
    strategy: str = ""
    sources: list[Source] = field(default_factory=list)


@dataclass(frozen=True)
class TeamDiscussionDraft:
    agent: AgentRole
    content: str


def _limit_sentences(text: str, max_sentences: int) -> str:
    parts = [p for p in re.split(r"(?<=[。！？.!?])\s*", text.strip()) if p]
    if len(parts) <= max_sentences:
        return text.strip()
    trimmed = "".join(parts[:max_sentences]).strip()
    if trimmed and trimmed[-1] not in "。！？.!?":
        trimmed += "。"
    return trimmed


def _position_from_message(debate: DebateState, message, side: str) -> int | None:
    agent = next((a for a in debate.agents if a.id == message.speaker_id), None)
    if agent:
        return agent.position
    if message.speech_flag is not None and debate_user_side(debate) == side:
        return debate_user_position(debate)
    return None


def positions_spoken_in_team_segment(debate: DebateState, side: str) -> set[int]:
    positions: set[int] = set()
    label = debate.segment_label or ""
    for message in debate.messages:
        if message.side != side or message.segment_label != label:
            continue
        position = _position_from_message(debate, message, side)
        if position is not None:
            positions.add(position)
    return positions


def human_positions_for_side(debate: DebateState, side: str) -> set[int]:
    return {
        p.position
        for p in debate.participants
        if p.side == side and p.position in {1, 2, 3, 4}
    }


def team_discussion_speakers(debate: DebateState, active_agent: AgentRole) -> list[AgentRole]:
    if active_agent.side not in {"affirmative", "negative"}:
        return []
    spoken = positions_spoken_in_team_segment(debate, active_agent.side)
    human_positions = human_positions_for_side(debate, active_agent.side)
    speakers: list[AgentRole] = []
    for position in range(1, 5):
        if position in spoken or position in human_positions:
            continue
        teammate = next(
            (
                agent
                for agent in debate.agents
                if agent.side == active_agent.side and agent.position == position
            ),
            None,
        )
        if teammate is not None:
            speakers.append(teammate)
    return speakers


def argument_ids_for_prompt(debate: DebateState, side: str) -> str:
    if side not in {"affirmative", "negative"}:
        return "（暂无）"
    ids = [item.id for item in debate.argument_bank.get(side, []) if item.id]
    return "、".join(ids) if ids else "（暂无）"


def ensure_team_discussion_argument_id(
    debate: DebateState,
    side: str,
    position: int,
    content: str,
) -> str:
    ids = sorted(item.id for item in debate.argument_bank.get(side, []) if item.id)
    if referenced_argument_ids(content):
        return content
    prefix = {"affirmative": "AFF", "negative": "NEG"}.get(side)
    if not prefix:
        return content
    preferred_id = ids[min(max(position - 1, 0), len(ids) - 1)] if ids else f"{prefix}-{max(position, 1)}"
    return f"{content.rstrip()} 我负责把 [{preferred_id}] 用在这一轮策略里。"


def build_team_discussion_user_content(
    debate: DebateState,
    context: TeamDiscussionContext,
    agent: AgentRole,
) -> str:
    ai_context = build_ai_debater_context(debate, agent, context.sources)
    return (
        f"辩题：{debate.topic}\n环节规则：{debate.segment_rules}\n"
        f"本轮任务：{context.stance_action or '队内讨论'}\n"
        f"策略：{context.strategy}\n"
        f"上一位对手公开发言（需优先回应；不含对方队内密谈）：\n{ai_context.opponent_last}\n"
        f"对手上一条是否低信息量/明显让步：{'是' if ai_context.opponent_last_is_low_information else '否'}\n"
        f"我方最近发言（避免与我方重复）：\n{ai_context.self_last}\n"
        f"我方可用论据库：\n{format_argument_bank(ai_context.own_argument_bank)}\n"
        f"对方可见论据库：\n{format_argument_bank(ai_context.opponent_argument_bank)}\n"
        f"可参考事实（只作为底层依据，不要逐条复述）：\n{ai_context.source_text}\n"
        f"辩论历史（仅含你方可见内容）：\n{ai_context.visible_history}\n"
        f"发送策略：{'；'.join(ai_context.policy_notes) or '按当前可见性发送数据。'}"
        "\n当前处于队内交流：若上一条已是任务分配，本条必须改为短句接话与补充，不得逐段复述分工。"
    )


def single_teammate_prompt(
    debate: DebateState,
    context: TeamDiscussionContext,
    agent: AgentRole,
) -> list[dict[str, str]]:
    side_label = "正方" if agent.side == "affirmative" else "反方"
    position_label = f"{agent.position}辩"
    ids = argument_ids_for_prompt(debate, agent.side)
    return [
        {
            "role": "system",
            "content": (
                f"你是{side_label}{position_label}，正在队内讨论，不是公开发言。"
                f"当前只能代表{side_label}{position_label}本人，不得冒充或代写一辩、其他辩位、主席或裁判。"
                "只输出你自己这一名辩手的一段话，八十到一百六十个汉字。"
                "不得写成立论陈词、驳论稿、质辩稿或总结陈词，不要称呼主席、评委、对方辩友。"
                "必须围绕本方论据库里的真实事实和本轮分工说话，不能编造不存在的数据、论文、法规。"
                f"本方可用论据 ID：{ids}。你的发言必须至少提到一个论据 ID，或明确说明你负责如何使用其中一组论据。"
                f"{segment_prompt_hint(debate)}"
                "语言自然，像队友在赛前快速确认策略。"
            ),
        },
        {"role": "user", "content": build_team_discussion_user_content(debate, context, agent)},
    ]


def _fallback_discussion_content(debate: DebateState, teammate: AgentRole) -> str:
    ids = sorted(argument_ids_for_side(debate, teammate.side))
    first_id = ids[0] if ids else ""
    fallback = {
        1: "我先把定义和判断标准收住，所有事实论据都从论据库里取，不再临场补虚例。",
        2: "我负责把第一轮最强事实接到反驳里，避免只讲态度，尽量用论据 ID 固定证据来源。",
        3: "我负责追问对方事实缺口，遇到知识性判断时要求对方给来源、给范围、给比较对象。",
        4: "我负责收束价值和胜负标准，把本方论据转成裁判能直接比较的战场。",
    }
    content = fallback.get(teammate.position, fallback[1])
    if first_id:
        content = f"{content} 我会优先把 [{first_id}] 接到本轮战场里，先讲事实，再讲它为什么能支撑我们的判断标准。"
    return content


async def generate_team_discussion_draft(
    debate: DebateState,
    context: TeamDiscussionContext,
    teammate: AgentRole,
    *,
    chat_completion_fn: ChatCompletionFn = chat_completion,
) -> TeamDiscussionDraft:
    try:
        content = await chat_completion_fn(
            single_teammate_prompt(debate, context, teammate),
            model=resolve_model(phase=debate.phase, speaker_id=teammate.id),
            temperature=0.62,
            max_tokens=420,
            debate_id=debate.id,
            operation=f"team_discussion_{teammate.id}",
        )
        content = _limit_sentences(strip_model_reasoning(content), 3)
    except DeepSeekError:
        content = _fallback_discussion_content(debate, teammate)
    ids = sorted(argument_ids_for_side(debate, teammate.side))
    if ids and not referenced_argument_ids(content):
        content = ensure_team_discussion_argument_id(debate, teammate.side, teammate.position, content)
    content = ensure_team_discussion_argument_id(debate, teammate.side, teammate.position, content)
    return TeamDiscussionDraft(agent=teammate, content=content)
