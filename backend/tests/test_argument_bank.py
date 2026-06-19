from app.models import ArgumentBankItem, DebateMessage, DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.models import Source
from app.services.argument_bank import (
    add_argument_items,
    add_message_arguments_to_bank,
    add_sources_to_argument_bank,
    build_argument_bank_from_sources,
    build_argument_bank_items,
    enforce_argument_citations,
)


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


def test_argument_bank_filters_generic_or_wrong_side_sources() -> None:
    sources = [
        Source(id="kb-debate-scoring", title="辩论礼仪", excerpt="逻辑一致性与证据可验证性是评分核心。"),
        Source(id="kb-topic", title="辩题上下文", excerpt="人工智能是否会提升青少年的综合学习能力"),
        Source(id="mat-risk", title="韩国AI作业禁令", excerpt="韩国限制小学生用 AI 完成家庭作业，担心主动思考下降。"),
        Source(id="mat-feedback", title="AI作业批改调研", excerpt="某省重点中学引入 AI 作业批改系统后，学生错题订正率提升近30%。"),
        Source(id="mat-generic", title="AI学习", excerpt="AI 个性化反馈帮助学生精准发现知识漏洞，提升错题复盘效率。"),
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert [item.title for item in bank["affirmative"]] == ["AI作业批改订正率提升", "AI个性化反馈发现漏洞"]
    assert [item.title for item in bank["negative"]] == ["韩国AI作业禁令"]


def test_sources_incrementally_enter_argument_bank_after_initial_lock() -> None:
    debate = _debate()
    first = [Source(title="即时反馈资料", excerpt="AI 个性化反馈帮助学生发现知识漏洞。")]
    second = [Source(title="韩国AI作业禁令", excerpt="2024年韩国教育部门限制小学生用 AI 完成家庭作业，担心主动思考下降。")]

    added_first = add_sources_to_argument_bank(debate, first)
    added_second = add_sources_to_argument_bank(debate, second)

    assert added_first["affirmative"] >= 1
    assert added_second["negative"] >= 1
    assert any(item.title == "韩国AI作业禁令" for item in debate.argument_bank["negative"])
    assert len({item.id for item in debate.argument_bank["negative"]}) == len(debate.argument_bank["negative"])


def test_ai_message_sources_and_new_claims_are_saved_as_arguments() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="neg_2",
        speaker_name="星白",
        side="negative",
        phase="rebuttal",
        segment_label="反方二辩回应",
        content=(
            "对方忽略了韩国AI作业禁令这一事实。"
            "韩国AI作业禁令说明，AI 会替代学生完成检索和思考，长期削弱主动学习能力。"
        ),
        sources=[
            Source(title="韩国AI作业禁令", excerpt="2024年韩国教育部门限制小学生用 AI 完成家庭作业。"),
        ],
    )

    added = add_message_arguments_to_bank(debate, message)

    assert added["negative"] >= 1
    assert any("韩国AI作业禁令" == item.title for item in debate.argument_bank["negative"])
    assert any("主动学习" in item.claim or "家庭作业" in item.claim for item in debate.argument_bank["negative"])


def test_ai_message_argument_title_prefers_concrete_case_not_speaker_setup() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="云汐",
        side="affirmative",
        phase="opening_prep",
        segment_label="正方队内讨论",
        content=(
            "我作为一辩先定定义和框架，第一论点 AI 个性化反馈能精准发现知识漏洞、提升效率我来主讲，"
            "例子上用那篇“某省重点中学引入AI作业批改系统后学生错题订正率提升近30%”的调研。"
        ),
    )

    add_message_arguments_to_bank(debate, message)

    titles = [item.title for item in debate.argument_bank["affirmative"]]
    assert "AI作业批改订正率提升" in titles
    assert all(not title.startswith("我作为") for title in titles)
