import pytest

from app.models import ArgumentBankItem, DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.assist import _assist_messages, _fallback_assist, _parse_assist
from app.services.draft_assist import _draft_messages, _fallback_draft


def _debate() -> DebateState:
    debate = DebateState(
        topic="人工智能是否会提升青少年的综合学习能力",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=90,
        format="formal",
        phase="opening_prep",
        segment_label="立论前准备 · 正方队内讨论(立论)",
        user_side="affirmative",
        user_position=2,
        agents=default_agents(),
        workflow=workflow_template(),
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
    return debate


def _joined_messages(messages: list[dict]) -> str:
    return "\n".join(str(message.get("content", "")) for message in messages)


def test_draft_prompt_uses_user_position_and_argument_bank_ids(monkeypatch) -> None:
    monkeypatch.setattr("app.services.draft_assist.retrieve_sources", lambda *_args, **_kwargs: [])
    debate = _debate()

    messages, sources, segment = _draft_messages(debate, "affirmative", "请帮我准备二辩队内讨论", position=2)
    prompt = _joined_messages(messages)

    assert sources == []
    assert segment == "立论前准备 · 正方队内讨论(立论)"
    assert "正方二辩" in prompt
    assert "队内讨论" in prompt
    assert "不是正式立论" in prompt
    assert "AFF-1" in prompt
    assert "kb-" not in prompt.lower()
    assert "正方一辩立论" not in prompt


def test_draft_fallback_cites_argument_bank_id_not_kb() -> None:
    debate = _debate()

    text = _fallback_draft(debate, "affirmative", [], debate.segment_label, position=2)

    assert "正方二辩" in text
    assert "AFF-1" in text
    assert "kb-" not in text.lower()
    assert "主席好" not in text


def test_assist_prompt_and_fallback_use_argument_bank_ids(monkeypatch) -> None:
    monkeypatch.setattr("app.services.assist.retrieve_sources", lambda *_args, **_kwargs: [])
    debate = _debate()

    messages, sources = _assist_messages(debate, "affirmative", "我想追问反馈效率", position=2)
    prompt = _joined_messages(messages)
    fallback = _fallback_assist("affirmative", sources, debate)

    assert "正方二辩" in prompt
    assert "AFF-1" in prompt
    assert "kb-" not in prompt.lower()
    assert any("AFF-1" in line for line in fallback["possible_lines"])
    assert "kb-" not in str(fallback).lower()


def test_parse_assist_discards_kb_citations_and_keeps_argument_ids() -> None:
    debate = _debate()
    sources = []
    raw = '{"suggestion":"追问对方证据缺口 [kb-a]，再回到即时反馈 [AFF-1]。","counter_rebuttal":"用 [kb-a] 会失败。","possible_lines":["请回应 [AFF-1]。","不要用 [kb-a]。"],"cite_ids":["kb-a","AFF-1"]}'

    parsed = _parse_assist(raw, "affirmative", sources, debate)

    assert "[AFF-1]" in parsed["suggestion"]
    assert "kb-" not in parsed["suggestion"].lower()
    assert all("kb-" not in line.lower() for line in parsed["possible_lines"])
