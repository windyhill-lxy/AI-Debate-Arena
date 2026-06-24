"""工作流集成测试：裁判流程快路径 + Mock LLM 完整回合。"""

import pytest

from app.models import ArgumentBankItem, DebateMessage, DebateMode, DebateState, DebateTiming, DebateVisibility, Source, default_agents, workflow_template
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


def _fill_opening_argument_bank(debate: DebateState) -> None:
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(id=f"AFF-{index}", side="affirmative", title=f"正方事实{index}", claim=f"2024年正方事实{index}。")
        for index in range(1, 11)
    ]
    debate.argument_bank["negative"] = [
        ArgumentBankItem(id=f"NEG-{index}", side="negative", title=f"反方事实{index}", claim=f"2024年反方事实{index}。")
        for index in range(1, 11)
    ]


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
        if seg and seg.phase == "opening_statement" and seg.speaker_side == "affirmative":
            apply_segment(debate, index)
            break
    _fill_opening_argument_bank(debate)

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
        if seg and seg.phase == "opening_statement" and seg.speaker_side == "negative":
            apply_segment(debate, index)
            break
    _fill_opening_argument_bank(debate)

    monkeypatch.setattr(
        "app.workflow.debate_graph.retrieve_sources",
        lambda *_args, **_kwargs: [
            Source(title="韩国AI作业禁令", excerpt="2024年韩国教育部门限制小学生用 AI 完成家庭作业，担心主动思考下降。"),
        ],
    )

    result = await debate_graph.run_turn_streaming(debate)

    assert any(item.title == "韩国AI作业禁令" for item in result.argument_bank["negative"])


@pytest.mark.asyncio
async def test_opening_fact_check_requires_all_own_argument_bank_ids() -> None:
    debate = _debate()
    apply_segment(debate, 10)
    debate.phase = "opening_statement"
    debate.segment_label = "正方一辩立论"
    debate.active_speaker_id = "aff_1"
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(id="AFF-1", side="affirmative", title="反馈事实", claim="2024年机构报告显示反馈提升。"),
        ArgumentBankItem(id="AFF-2", side="affirmative", title="复盘事实", claim="2023年研究显示复盘改善迁移。"),
    ]
    draft = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="云汐",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="我方用反馈事实证明能力提升 [AFF-1]。",
    )

    state = {"debate": debate, "draft_message": draft}
    checked = await debate_graph._fact_check(state)

    assert checked["facts_ok"] is False
    assert checked["draft_message"].hallucination_risk == "high"


@pytest.mark.asyncio
async def test_opening_evidence_retrieve_seeds_ten_arguments_per_side(monkeypatch) -> None:
    debate = _debate()
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and seg.id == "opening_evidence_bank":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing opening evidence bank segment")

    calls = {"affirmative": 0, "negative": 0}

    async def fake_search(_debate: DebateState, side: str) -> list[Source]:
        calls[side] += 1
        offset = (calls[side] - 1) * 5
        if side == "affirmative":
            return [
                Source(
                    title=f"正方AI反馈研究{offset + i}",
                    excerpt=f"202{offset + i % 5}年教育机构报告显示，AI 个性化反馈帮助学生发现知识漏洞，学习效率提升{20 + i}%。",
                )
                for i in range(1, 6)
            ]
        return [
            Source(
                title=f"反方AI依赖调查{offset + i}",
                excerpt=f"202{offset + i % 5}年教育机构调查显示，频繁使用 AI 解题导致自主解题能力下降{10 + i}%。",
            )
            for i in range(1, 6)
        ]

    monkeypatch.setattr("app.services.opening_evidence.search_real_evidence_with_ai", fake_search)
    monkeypatch.setattr("app.services.opening_evidence.retrieve_sources", lambda *_args, **_kwargs: [])

    result = await debate_graph.run_turn_streaming(debate)

    assert len(result.argument_bank["affirmative"]) >= 10
    assert len(result.argument_bank["negative"]) >= 10
    assert result.argument_bank_locked is True
    assert calls["affirmative"] >= 2
    assert calls["negative"] >= 2


@pytest.mark.asyncio
async def test_opening_evidence_retrieve_emits_incremental_argument_bank_updates(monkeypatch) -> None:
    debate = _debate()
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and seg.id == "opening_evidence_bank":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing opening evidence bank segment")

    async def fake_search(_debate: DebateState, side: str) -> list[Source]:
        if side == "affirmative":
            return [
                Source(
                    title="正方反馈研究",
                    excerpt="2024年教育机构报告显示，AI 个性化反馈帮助学生发现知识漏洞，学习效率提升21%。",
                )
            ]
        return [
            Source(
                title="反方依赖调查",
                excerpt="2024年教育机构调查显示，频繁使用 AI 解题导致自主解题能力下降12%。",
            )
        ]

    monkeypatch.setattr("app.services.opening_evidence.search_real_evidence_with_ai", fake_search)
    monkeypatch.setattr("app.services.opening_evidence.retrieve_sources", lambda *_args, **_kwargs: [])
    events: list[dict] = []

    await debate_graph.run_turn_streaming(debate, on_event=events.append)

    updates = [event for event in events if event.get("type") == "argument_bank_updated"]
    assert updates
    assert updates[0]["side"] == "affirmative"
    assert updates[0]["argument_bank"]["affirmative"]
    assert updates[0]["affirmative_count"] >= 1
    assert any(event.get("type") == "argument_bank_seeded" for event in events)


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
    _fill_opening_argument_bank(debate)

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
async def test_opening_team_discussion_each_affirmative_debater_uses_argument_bank(monkeypatch) -> None:
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
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(id=f"AFF-{index}", side="affirmative", title=f"正方论据{index}", claim=f"2024年报告显示正方论据{index}。")
        for index in range(1, 11)
    ]
    debate.argument_bank["negative"] = [
        ArgumentBankItem(id=f"NEG-{index}", side="negative", title=f"反方论据{index}", claim=f"2024年报告显示反方论据{index}。")
        for index in range(1, 11)
    ]
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="云汐",
            side="affirmative",
            phase="opening_prep",
            segment_label="立论前准备 · 一辩任务分配",
            content="一辩任务分配已经完成。",
        )
    )
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(id=f"AFF-{index}", side="affirmative", title=f"正方论据{index}", claim=f"2024年报告显示正方论据{index}。")
        for index in range(1, 11)
    ]

    async def fake_chat_completion(*_args, **_kwargs):
        return "我负责把这一轮策略接到论据库里，先讲事实，再把它转成我们的比较标准。"

    monkeypatch.setattr("app.workflow.debate_graph.chat_completion", fake_chat_completion)

    result = await debate_graph.run_turn_streaming(debate)
    added = result.messages[-4:]

    assert [m.speaker_id for m in added] == ["aff_1", "aff_2", "aff_3", "aff_4"]
    assert len({m.speaker_id for m in added}) == 4
    assert all(m.phase == "opening_prep" for m in added)
    assert all("AFF-" in m.content for m in added)


@pytest.mark.asyncio
async def test_opening_evidence_gate_pauses_when_argument_bank_not_ready(monkeypatch) -> None:
    from app.services.opening_evidence import OpeningEvidenceResult

    debate = _debate()
    debate.schedule_template = "formal_4v4"
    init_schedule(debate)
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and seg.id == "opening_evidence_bank":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing opening evidence segment")

    async def not_ready(*_args, **_kwargs):
        return OpeningEvidenceResult(
            added={"affirmative": 0, "negative": 0},
            sources=[],
            ready=False,
        )

    monkeypatch.setattr("app.workflow.debate_graph.ensure_opening_argument_bank", not_ready)
    before_index = debate.schedule_index

    result = await debate_graph.run_turn_streaming(debate)

    assert result.schedule_index == before_index
    assert result.messages == []
    assert result.auto_running is False
    assert result.awaiting_user is False


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
    _fill_opening_argument_bank(debate)

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


@pytest.mark.asyncio
async def test_team_discussion_skips_rag_retrieval(monkeypatch) -> None:
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

    async def fake_chat_completion(*_args, **_kwargs):
        return "我负责把本方论据接到这一轮策略里，先讲事实，再讲判断标准。"

    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(id=f"AFF-{index}", side="affirmative", title=f"正方论据{index}", claim=f"2024年报告显示正方论据{index}。")
        for index in range(1, 11)
    ]
    debate.argument_bank["negative"] = [
        ArgumentBankItem(id=f"NEG-{index}", side="negative", title=f"反方论据{index}", claim=f"2024年报告显示反方论据{index}。")
        for index in range(1, 11)
    ]

    def fail_retrieve(*_args, **_kwargs):
        raise AssertionError("team discussion should not run RAG retrieval")

    monkeypatch.setattr("app.workflow.debate_graph.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.workflow.debate_graph.retrieve_sources", fail_retrieve)

    result = await debate_graph.run_turn_streaming(debate)

    assert result.messages
    assert all(is_internal_message(message) for message in result.messages[-4:])


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
