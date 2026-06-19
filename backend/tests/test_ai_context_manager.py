from app.models import AgentRole, ArgumentBankItem, DebateMessage, DebateState, DebateTiming, DebateVisibility
from app.services.ai_context_manager import build_ai_debater_context


def _agent(id_: str, side: str, position: int) -> AgentRole:
    return AgentRole(
        id=id_,
        name=id_,
        side=side,
        position=position,
        avatar="/avatar.png",
        model="test-model",
        persona="test persona",
    )


def test_build_ai_debater_context_sends_only_current_debater_allowed_data() -> None:
    aff = _agent("aff_1", "affirmative", 1)
    neg = _agent("neg_1", "negative", 1)
    debate = DebateState(
        topic="中学生是否应该使用 AI 辅助写作",
        mode="ai_autonomous",
        visibility=DebateVisibility.own_side_only,
        timing=DebateTiming.limited,
        turn_seconds=90,
        format="formal",
        agents=[aff, neg],
        phase="opening_statement",
        segment_label="正方一辩立论",
        segment_rules="完成开篇立论。",
        active_speaker_id="aff_1",
        argument_bank={
            "affirmative": [
                ArgumentBankItem(id="AFF-1", side="affirmative", title="AI 即时反馈", claim="AI 能即时反馈写作问题。")
            ],
            "negative": [
                ArgumentBankItem(id="NEG-1", side="negative", title="依赖风险", claim="过度依赖会削弱独立思考。")
            ],
        },
        messages=[
            DebateMessage(
                debate_id="debate-1",
                speaker_id="neg_1",
                speaker_name="反方一辩",
                side="negative",
                content="公开反驳内容",
                phase="opening_statement",
            ),
            DebateMessage(
                debate_id="debate-1",
                speaker_id="neg_1",
                speaker_name="反方一辩",
                side="negative",
                content="反方队内密谈",
                phase="opening_prep",
                private_thought="private",
            ),
        ],
    )

    context = build_ai_debater_context(debate, aff, [])

    assert context.own_argument_bank[0].id == "AFF-1"
    assert [item.id for item in context.opponent_argument_bank] == []
    assert context.opponent_last == "公开反驳内容"
    assert "反方队内密谈" not in context.visible_history
    assert "公开反驳内容" in context.visible_history
