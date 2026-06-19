from app.models import ArgumentBankItem, DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.models import Source
from app.services.argument_bank import add_argument_items, build_argument_bank_from_sources, build_argument_bank_items, enforce_argument_citations


def _debate() -> DebateState:
    return DebateState(
        topic="论据库测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.all_visible,
        timing=DebateTiming.limited,
        turn_seconds=90,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
    )


def test_argument_bank_partitions_by_side_and_enforces_ids() -> None:
    debate = _debate()
    add_argument_items(
        debate,
        "affirmative",
        [
            ArgumentBankItem(id="AFF-1", side="affirmative", claim="即时反馈提升训练效率", source="预置资料"),
        ],
    )
    add_argument_items(
        debate,
        "negative",
        [
            ArgumentBankItem(id="NEG-1", side="negative", claim="过度依赖会削弱主动回忆", source="预置资料"),
        ],
    )

    assert len(debate.argument_bank["affirmative"]) == 1
    assert len(debate.argument_bank["negative"]) == 1
    assert enforce_argument_citations(debate, "affirmative", "我方引用 [AFF-1] 说明训练效率。")[0] is True
    ok, reason = enforce_argument_citations(debate, "affirmative", "我方凭常识认为肯定有效。")
    assert ok is False
    assert "论据库" in reason


def test_build_argument_bank_items_creates_stable_positive_and_negative_ids() -> None:
    claims = {
        "affirmative": ["即时反馈能缩短训练闭环", "多轮追问能暴露逻辑漏洞"],
        "negative": ["过度依赖会削弱主动检索", "模型可能给出未经证实的案例"],
    }

    bank = build_argument_bank_items(claims, source="AI 预生成论据库")

    assert [item.id for item in bank["affirmative"]] == ["AFF-1", "AFF-2"]
    assert [item.id for item in bank["negative"]] == ["NEG-1", "NEG-2"]
    assert bank["affirmative"][0].side == "affirmative"
    assert bank["negative"][0].source == "AI 预生成论据库"


def test_build_argument_bank_items_creates_short_readable_titles() -> None:
    claims = {
        "affirmative": ["即时反馈能缩短训练闭环，让辩手快速发现论证漏洞"],
        "negative": ["模型可能给出未经证实的案例，导致立论事实基础不稳"],
    }

    bank = build_argument_bank_items(claims, source="AI 预生成论据库")

    assert bank["affirmative"][0].title == "即时反馈缩短训练闭环"
    assert bank["negative"][0].title == "模型案例未经证实"
    assert len(bank["affirmative"][0].title) <= 14


def test_build_argument_bank_from_sources_uses_natural_titles() -> None:
    sources = [
        Source(title="课堂反馈研究", excerpt="AI 能提供即时反馈，帮助学生更快修正写作和表达问题。"),
        Source(title="工具依赖风险", excerpt="过度依赖 AI 会削弱自主检索、资料辨别和长期专注能力。"),
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert bank["affirmative"][0].id == "AFF-1"
    assert bank["negative"][0].id == "NEG-1"
    assert bank["affirmative"][0].title
    assert bank["negative"][0].title
    assert "未找到" not in bank["affirmative"][0].claim
