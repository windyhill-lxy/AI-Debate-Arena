from __future__ import annotations

from dataclasses import dataclass

from app.models import AgentRole, ArgumentBankItem, DebateState, Source
from app.services.message_visibility import format_debate_history, latest_message_for_viewer


INTERNAL_TEAM_PHASES = frozenset({"opening_prep", "free_prep", "closing_prep"})


@dataclass(frozen=True)
class AIDebaterContext:
    topic: str
    segment_label: str
    segment_rules: str
    viewer_side: str
    opponent_side: str
    source_text: str
    own_argument_bank: list[ArgumentBankItem]
    opponent_argument_bank: list[ArgumentBankItem]
    visible_history: str
    opponent_last: str
    self_last: str
    opponent_last_is_low_information: bool
    policy_notes: list[str]


def _looks_low_information_message(text: str) -> bool:
    compact = "".join((text or "").split())
    return len(compact) < 24 or compact in {"同意", "好的", "继续", "没有问题"}


def _argument_bank_for(debate: DebateState, side: str) -> list[ArgumentBankItem]:
    if side not in {"affirmative", "negative"}:
        return []
    return list((debate.argument_bank or {}).get(side, []))


def _format_sources(sources: list[Source]) -> str:
    return "\n".join(f"【{s.title}】 {s.excerpt}" for s in sources) or "无可靠外部资料，请明确表达不确定。"


def build_ai_debater_context(
    debate: DebateState,
    agent: AgentRole,
    sources: list[Source],
) -> AIDebaterContext:
    viewer_side = agent.side if agent.side in {"affirmative", "negative", "judge"} else "judge"
    opponent_side = "negative" if agent.side == "affirmative" else "affirmative"
    in_internal_phase = debate.phase in INTERNAL_TEAM_PHASES
    opponent_last = latest_message_for_viewer(
        debate.messages,
        opponent_side,
        viewer_side,
        in_internal_phase=in_internal_phase,
        public_only=True,
    )
    self_last = latest_message_for_viewer(
        debate.messages,
        agent.side,
        viewer_side,
        in_internal_phase=in_internal_phase,
    )
    can_see_opponent_bank = debate.visibility in {"god", "all_visible"} and not in_internal_phase
    policy_notes: list[str] = []
    if in_internal_phase:
        policy_notes.append("当前为队内准备阶段，不发送对方队内密谈。")
    if not can_see_opponent_bank:
        policy_notes.append("当前不发送对方论据库，只发送本方可用论据。")

    return AIDebaterContext(
        topic=debate.topic,
        segment_label=debate.segment_label,
        segment_rules=debate.segment_rules,
        viewer_side=viewer_side,
        opponent_side=opponent_side,
        source_text=_format_sources(sources),
        own_argument_bank=_argument_bank_for(debate, agent.side),
        opponent_argument_bank=_argument_bank_for(debate, opponent_side) if can_see_opponent_bank else [],
        visible_history=format_debate_history(
            debate.messages,
            viewer_side=viewer_side,
            in_internal_phase=in_internal_phase,
        ),
        opponent_last=(
            opponent_last.content[:600]
            if opponent_last
            else ("（对方尚无公开发言；勿引用或臆测对方队内讨论）" if in_internal_phase else "（暂无）")
        ),
        self_last=(self_last.content[:400] if self_last else "（暂无）"),
        opponent_last_is_low_information=bool(opponent_last and _looks_low_information_message(opponent_last.content)),
        policy_notes=policy_notes,
    )


def format_argument_bank(items: list[ArgumentBankItem]) -> str:
    if not items:
        return "（暂无）"
    return "\n".join(f"{item.id} {item.title or item.claim[:18]}：{item.claim}" for item in items)
