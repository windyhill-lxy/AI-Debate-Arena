"""工作流集成测试：裁判流程快路径 + Mock LLM 完整回合。"""

import pytest

from app.models import ArgumentBankItem, DebateMode, DebateState, DebateTiming, DebateVisibility, Source, default_agents, workflow_template
from app.services.debate_schedule import apply_segment, get_segment, init_schedule
from app.services.debate_schedule_meta import is_procedural_segment
from app.services.message_visibility import is_internal_message, is_public_message
from app.workflow.debate_graph import debate_graph


def _debate() -> DebateState:
    agents = default_agents()
    debate = DebateState(
        topic="工作流集成测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=agents,
        workflow=workflow_template(),
        schedule_template="formal_4v4",
    )
    init_schedule(debate)
    return debate


@pytest.mark.asyncio
async def test_procedural_judge_segment_skips_llm(mock_llm_stream: None) -> None:
    debate = _debate()
    debate.schedule_template = "formal_4v4"
    init_schedule(debate)
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and "RAG" in (seg.label or "") and seg.speaker_side == "judge":
            apply_segment(debate, index)
            assert is_procedural_segment(debate) is True
            before_msgs = len(debate.messages)
            before_turn = debate.turn_index
            result = await debate_graph.run_turn_streaming(debate)
            assert len(result.messages) == before_msgs
            assert result.turn_index == before_turn + 1
            return
    pytest.skip("no procedural judge segment in formal_4v4")


@pytest.mark.asyncio
async def test_mock_llm_turn_appends_message(mock_llm_stream: None) -> None:
    debate = _debate()
    for index in range(30):
        seg = get_segment(debate, index)
        if seg and seg.speaker_side in {"affirmative", "negative"}:
            apply_segment(debate, index)
            break

    events: list[str] = []

    async def on_event(evt: dict) -> None:
        events.append(evt.get("type", ""))

    result = await debate_graph.run_turn_streaming(debate, on_event=on_event)
    assert len(result.messages) >= 1
    assert result.messages[-1].content
    assert "speech_start" in events
    assert "speech_chunk" in events
    assert "speech_end" in events


@pytest.mark.asyncio
async def test_rag_retrieve_populates_argument_bank(monkeypatch, mock_llm_stream: None) -> None:
    debate = _debate()
    for index in range(30):
        seg = get_segment(debate, index)
        if seg and seg.speaker_side == "affirmative":
            apply_segment(debate, index)
            break

    monkeypatch.setattr(
        "app.workflow.debate_graph.retrieve_sources",
        lambda *_args, **_kwargs: [
            Source(title="即时反馈资料", excerpt="2024年某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。"),
            Source(title="依赖风险资料", excerpt="2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。"),
        ],
    )

    result = await debate_graph.run_turn_streaming(debate)

    assert result.argument_bank_locked is True
    assert result.argument_bank["affirmative"]
    assert result.argument_bank["negative"]
    assert result.argument_bank["affirmative"][0].title


@pytest.mark.asyncio
async def test_rag_retrieve_keeps_adding_new_materials_after_argument_bank_exists(monkeypatch, mock_llm_stream: None) -> None:
    debate = _debate()
    for index in range(30):
        seg = get_segment(debate, index)
        if seg and seg.speaker_side == "negative":
            apply_segment(debate, index)
            break
    debate.argument_bank_locked = True
    debate.argument_bank["negative"].append(
        ArgumentBankItem(id="NEG-1", side="negative", title="旧资料", claim="旧资料", source="预置资料")
    )

    monkeypatch.setattr(
        "app.workflow.debate_graph.retrieve_sources",
        lambda *_args, **_kwargs: [
            Source(title="韩国AI作业禁令", excerpt="2024年韩国教育部门限制小学生用 AI 完成家庭作业，担心主动思考下降。"),
        ],
    )

    result = await debate_graph.run_turn_streaming(debate)

    assert any(item.title == "韩国AI作业禁令" for item in result.argument_bank["negative"])


@pytest.mark.asyncio
async def test_team_discussion_publishes_four_internal_debater_messages(monkeypatch) -> None:
    debate = _debate()
    debate.schedule_template = "formal_4v4"
    init_schedule(debate)
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and seg.id == "neg_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing negative opening discussion segment")

    async def fake_chat_completion(*_args, **_kwargs):
        return (
            "一辩：框架还是风险优先，别写成正式立论。\n"
            "二辩：我补思维依赖，用抄答案这个日常例子。\n"
            "三辩：我盯记忆抑制，强调主动回忆被削弱。\n"
            "四辩：我守替代标准，效率不等于能力。"
        )

    monkeypatch.setattr("app.workflow.debate_graph.chat_completion", fake_chat_completion)

    result = await debate_graph.run_turn_streaming(debate)
    added = result.messages[-4:]
    assert [m.speaker_id for m in added] == ["neg_1", "neg_2", "neg_3", "neg_4"]
    assert all(is_internal_message(m) for m in added)
    assert all(not is_public_message(m) for m in added)
    assert all("主席" not in m.content and "评委" not in m.content for m in added)


@pytest.mark.asyncio
async def test_internal_prep_skips_reflection_finalize(monkeypatch) -> None:
    debate = _debate()
    debate.schedule_template = "formal_4v4"
    init_schedule(debate)
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and seg.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing affirmative opening discussion segment")

    operations: list[str] = []

    async def fake_chat_completion(*_args, **kwargs):
        operations.append(kwargs.get("operation", ""))
        return (
            "一辩：我定框架。\n"
            "二辩：我补定义。\n"
            "三辩：我补攻击。\n"
            "四辩：我收束。"
        )

    monkeypatch.setattr("app.workflow.debate_graph.chat_completion", fake_chat_completion)

    await debate_graph.run_turn_streaming(debate)
    assert "reflection_finalize" not in operations


def test_procedural_ready_segments_skip_judge_speech() -> None:
    debate = _debate()
    debate.schedule_template = "formal_4v4"
    init_schedule(debate)
    labels = {
        "自由辩论前准备 · 暂停计时",
        "自由辩论前准备 · 准备就绪",
        "自由辩论环节 · 结束自由辩论",
    }
    seen = set()
    for index in range(160):
        seg = get_segment(debate, index)
        if seg and seg.label in labels:
            apply_segment(debate, index)
            seen.add(seg.label)
            assert is_procedural_segment(debate) is True
    assert seen == labels
