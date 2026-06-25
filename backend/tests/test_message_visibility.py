from datetime import datetime, timezone

from app.models import (
    ArgumentBankItem,
    DebateMessage,
    DebateMode,
    DebateState,
    DebateTiming,
    DebateVisibility,
    Source,
    default_agents,
)
from app.services.message_visibility import (
    format_debate_history,
    is_internal_message,
    is_public_message,
    latest_message_for_viewer,
    message_visible_to_side,
)
from app.services.viewer_payload import debate_payload_for_viewer


def _msg(
    *,
    side: str,
    content: str,
    phase: str = "opening_prep",
    segment_label: str = "一辩任务分配",
) -> DebateMessage:
    return DebateMessage(
        debate_id="d1",
        speaker_id="s1",
        speaker_name="测试",
        side=side,
        content=content,
        phase=phase,
        segment_label=segment_label,
        created_at=datetime.now(timezone.utc),
    )


def test_internal_prep_not_visible_to_opponent():
    aff_internal = _msg(side="affirmative", content="从小听周杰伦所以好听")
    assert is_internal_message(aff_internal)
    assert message_visible_to_side(aff_internal, "affirmative", in_internal_phase=True)
    assert not message_visible_to_side(aff_internal, "negative", in_internal_phase=True)


def test_public_statement_visible_to_both():
    public = _msg(
        side="affirmative",
        content="我方标准是可验证的学习成效",
        phase="opening_statement",
        segment_label="正方一辩立论",
    )
    assert is_public_message(public)
    assert message_visible_to_side(public, "negative", in_internal_phase=False)


def test_judge_warning_is_public_message():
    warning = _msg(
        side="judge",
        content="裁判警告：请重新发言。",
        phase="opening_statement",
        segment_label="裁判警告 · 正方三辩发言",
    )
    assert is_public_message(warning)
    assert message_visible_to_side(warning, "affirmative", in_internal_phase=False)
    assert message_visible_to_side(warning, "negative", in_internal_phase=False)


def test_format_history_excludes_opponent_internal():
    messages = [
        _msg(side="affirmative", content="队内秘密论点"),
        _msg(
            side="affirmative",
            content="公开立论",
            phase="opening_statement",
            segment_label="正方一辩立论",
        ),
    ]
    neg_history = format_debate_history(messages, viewer_side="negative", in_internal_phase=True)
    assert "队内秘密论点" not in neg_history
    assert "公开立论" in neg_history


def test_latest_opponent_public_skips_internal():
    messages = [
        _msg(side="affirmative", content="队内秘密"),
        _msg(
            side="affirmative",
            content="公开立论内容",
            phase="opening_statement",
            segment_label="正方一辩立论",
        ),
    ]
    last = latest_message_for_viewer(
        messages,
        "affirmative",
        "negative",
        in_internal_phase=False,
        public_only=True,
    )
    assert last is not None
    assert last.content == "公开立论内容"


def test_viewer_payload_context_keeps_strategy_for_own_side():
    debate = DebateState(
        topic="权限测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )
    internal = _msg(side="affirmative", content="正方内部秘密")
    internal.private_thought = "隐藏策略"
    internal.strategy = "隐藏路线"
    public = _msg(
        side="affirmative",
        content="公开发言",
        phase="opening_statement",
        segment_label="正方一辩立论",
    )
    public.private_thought = "公开消息的内部策略"
    public.strategy = "公开策略"
    debate.messages = [internal, public]

    negative = debate_payload_for_viewer(debate, viewer_side="negative", viewer_mode="context")
    assert [m["content"] for m in negative["messages"]] == ["公开发言"]
    assert negative["messages"][0]["private_thought"] is None
    assert negative["messages"][0]["strategy"] is None

    affirmative = debate_payload_for_viewer(debate, viewer_side="affirmative", viewer_mode="context")
    contents = [m["content"] for m in affirmative["messages"]]
    assert "正方内部秘密" in contents
    assert "公开发言" in contents
    public_msg = next(m for m in affirmative["messages"] if m["content"] == "公开发言")
    assert public_msg["private_thought"] == "公开消息的内部策略"
    assert public_msg["strategy"] == "公开策略"


def test_viewer_payload_realistic_strips_strategy_fields():
    debate = DebateState(
        topic="权限测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )
    public = _msg(
        side="affirmative",
        content="公开发言",
        phase="opening_statement",
        segment_label="正方一辩立论",
    )
    public.private_thought = "不应下发"
    public.strategy = "不应下发"
    debate.messages = [public]

    payload = debate_payload_for_viewer(debate, viewer_side="affirmative", viewer_mode="realistic")
    assert payload["messages"][0]["private_thought"] is None
    assert payload["messages"][0]["strategy"] is None


def test_viewer_payload_god_mode_shows_both_internal():
    debate = DebateState(
        topic="全知测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )
    aff_internal = _msg(side="affirmative", content="正方内部")
    neg_internal = _msg(side="negative", content="反方内部")
    debate.messages = [aff_internal, neg_internal]

    payload = debate_payload_for_viewer(debate, viewer_side="negative", viewer_mode="god")
    contents = [m["content"] for m in payload["messages"]]
    assert "正方内部" in contents
    assert "反方内部" in contents


def test_viewer_payload_never_filters_opponent_argument_bank():
    debate = DebateState(
        topic="论据库公开测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        user_side="affirmative",
        user_position=2,
    )
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(
            id="AFF-1",
            side="affirmative",
            title="AI作业批改订正率提升",
            claim="2024年某省重点中学引入 AI 作业批改系统后，学生错题订正率提升近30%。",
            source="AI 检索真实论据入库",
        )
    ]
    debate.argument_bank["negative"] = [
        ArgumentBankItem(
            id="NEG-1",
            side="negative",
            title="AI解题后自主解题下降",
            claim="2021年一项针对高中生的调查显示，频繁使用 AI 解题后自主解题能力下降。",
            source="AI 检索真实论据入库",
        )
    ]

    payload = debate_payload_for_viewer(debate, viewer_side="affirmative", viewer_mode="own_side_only")

    assert [item["id"] for item in payload["argument_bank"]["affirmative"]] == ["AFF-1"]
    assert [item["id"] for item in payload["argument_bank"]["negative"]] == ["NEG-1"]


def test_auto_runner_payload_filters_internal_messages():
    from app.services.auto_runner import _payload_for_connection

    debate = DebateState(
        topic="自动广播权限测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
    )
    debate.messages = [
        _msg(side="affirmative", content="正方内部秘密"),
        _msg(
            side="negative",
            content="反方公开发言",
            phase="opening_statement",
            segment_label="反方一辩立论",
        ),
    ]
    negative = _payload_for_connection(debate, viewer_side="negative", viewer_mode="context")
    contents = [m["content"] for m in negative["messages"]]
    assert "正方内部秘密" not in contents
    assert "反方公开发言" in contents
