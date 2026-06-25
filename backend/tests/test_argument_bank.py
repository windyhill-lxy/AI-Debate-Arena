from app.models import ArgumentBankItem, DebateMessage, DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.models import Source
from app.services.argument_bank import (
    add_argument_items,
    add_message_arguments_to_bank,
    add_sources_to_argument_bank,
    add_sources_to_argument_bank_with_ai_titles,
    build_argument_bank_from_sources,
    build_argument_bank_items,
    enforce_argument_citations,
)
import pytest


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
        "affirmative": [
            "2020年，卡内基梅隆大学的一项教育实验发现，使用AI自适应学习平台的学生，在数学测评中识别自身知识薄弱点的准确率比对照组高出百分之三十七。",
            "某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。",
        ],
        "negative": [
            "2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。",
            "2024年韩国教育部门限制小学生用 AI 完成家庭作业。",
        ],
    }

    bank = build_argument_bank_items(claims, source="AI 预生成论据库")

    assert [item.id for item in bank["affirmative"]] == ["AFF-1", "AFF-2"]
    assert [item.id for item in bank["negative"]] == ["NEG-1", "NEG-2"]
    assert bank["affirmative"][0].side == "affirmative"
    assert bank["negative"][0].source == "AI 预生成论据库"


def test_build_argument_bank_items_creates_short_readable_titles() -> None:
    claims = {
        "affirmative": ["某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。"],
        "negative": ["2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。"],
    }

    bank = build_argument_bank_items(claims, source="AI 预生成论据库")

    assert bank["affirmative"][0].title == "AI作业批改订正率提升"
    assert bank["negative"][0].title == "AI解题后自主解题下降"
    assert len(bank["affirmative"][0].title) <= 14


def test_build_argument_bank_from_sources_uses_natural_titles() -> None:
    sources = [
        Source(title="课堂反馈研究", excerpt="2024年某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。"),
        Source(title="工具依赖风险", excerpt="2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。"),
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert bank["affirmative"][0].id == "AFF-1"
    assert bank["negative"][0].id == "NEG-1"
    assert bank["affirmative"][0].title
    assert bank["negative"][0].title
    assert "未找到" not in bank["affirmative"][0].claim


def test_argument_bank_title_is_refined_from_evidence_not_raw_prefix() -> None:
    sources = [
        Source(
            title="课堂观察资料",
            excerpt="2024年上海某区课堂观察显示，AI 口语陪练让学生课后英语口语练习频次提升42%。",
        )
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert bank["affirmative"][0].title == "AI口语陪练频次提升"
    assert not bank["affirmative"][0].title.startswith("来源")
    assert "2024年上海某区课堂观察显示" not in bank["affirmative"][0].title


@pytest.mark.asyncio
async def test_add_sources_uses_ai_summarized_titles_instead_of_clipped_excerpt(monkeypatch) -> None:
    debate = _debate()
    long_excerpt = "2024年上海某区课堂观察显示，AI 口语陪练让学生课后英语口语练习频次提升42%。"

    async def fake_chat_completion(messages, **kwargs):
        assert kwargs["operation"] == "argument_bank_title_summary"
        prompt = messages[-1]["content"]
        assert long_excerpt in prompt
        return '{"titles":[{"id":"AFF-1","title":"AI陪练提升口语频次"}]}'

    monkeypatch.setattr("app.services.argument_bank.chat_completion", fake_chat_completion)

    added = await add_sources_to_argument_bank_with_ai_titles(
        debate,
        [Source(title="课堂观察资料", excerpt=long_excerpt)],
    )

    assert added["affirmative"] == 1
    assert debate.argument_bank["affirmative"][0].title == "AI陪练提升口语频次"
    assert not debate.argument_bank["affirmative"][0].title.startswith("2024年上海某区")


def test_argument_bank_title_removes_year_prefix_from_source_excerpt() -> None:
    sources = [
        Source(
            title="学生AI解题依赖调查",
            excerpt="2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。",
        )
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert bank["negative"][0].title == "AI解题后自主解题下降"
    assert bank["negative"][0].title != "2021年"


def test_argument_bank_filters_generic_or_wrong_side_sources() -> None:
    sources = [
        Source(id="kb-debate-scoring", title="辩论礼仪", excerpt="逻辑一致性与证据可验证性是评分核心。"),
        Source(id="kb-topic", title="辩题上下文", excerpt="人工智能是否会提升青少年的综合学习能力"),
        Source(id="mat-risk", title="韩国AI作业禁令", excerpt="韩国限制小学生用 AI 完成家庭作业，担心主动思考下降。"),
        Source(id="mat-feedback", title="AI作业批改调研", excerpt="某省重点中学引入 AI 作业批改系统后，学生错题订正率提升近30%。"),
        Source(id="mat-generic", title="AI学习", excerpt="AI 个性化反馈帮助学生精准发现知识漏洞，提升错题复盘效率。"),
    ]

    bank = build_argument_bank_from_sources("人工智能是否会提升学习能力", sources)

    assert [item.title for item in bank["affirmative"]] == ["AI作业批改订正率提升"]
    assert [item.title for item in bank["negative"]] == ["韩国AI作业禁令"]


def test_argument_bank_only_accepts_factual_evidence_items() -> None:
    claims = {
        "affirmative": [
            "二辩你主要思维训练，找类似可汗学院AI引导解题的案例，强调启发式追问。",
            "认同框架，自主学习这块我上Duolingo自定进度的案例。",
            "2020年，卡内基梅隆大学的一项教育实验发现，使用AI自适应学习平台的学生，在数学测评中识别自身知识薄弱点的准确率比对照组高出百分之三十七。",
        ],
        "negative": [
            "我负责立论框架，重点讲AI带来的思维依赖风险。",
            "四辩总结时强化案例，比如有学生过度依赖AI导致考试翻车的真实报道。",
            "2021年一项针对高中生的调查显示，频繁使用AI解题后自主解题能力下降。",
        ],
    }

    bank = build_argument_bank_items(claims, source="AI 预生成论据库")

    assert [item.title for item in bank["affirmative"]] == ["AI自适应学习平台测评提升"]
    assert [item.title for item in bank["negative"]] == ["AI解题后自主解题下降"]
    assert all("我负责" not in item.claim and "二辩" not in item.claim and "认同框架" not in item.claim for item in bank["affirmative"] + bank["negative"])


def test_sources_incrementally_enter_argument_bank_after_initial_lock() -> None:
    debate = _debate()
    first = [Source(title="即时反馈资料", excerpt="2024年某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。")]
    second = [Source(title="韩国AI作业禁令", excerpt="2024年韩国教育部门限制小学生用 AI 完成家庭作业，担心主动思考下降。")]

    added_first = add_sources_to_argument_bank(debate, first)
    added_second = add_sources_to_argument_bank(debate, second)

    assert added_first["affirmative"] >= 1
    assert added_second["negative"] >= 1
    assert any(item.title == "韩国AI作业禁令" for item in debate.argument_bank["negative"])
    assert len({item.id for item in debate.argument_bank["negative"]}) == len(debate.argument_bank["negative"])


def test_ai_message_sources_are_saved_but_speech_claims_are_not_extracted() -> None:
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
    assert any("家庭作业" in item.claim for item in debate.argument_bank["negative"])
    assert not any(item.source.startswith("AI 发言入库") for item in debate.argument_bank["negative"])


def test_public_speech_claims_do_not_enter_argument_bank_without_sources() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_2",
        speaker_name="澜汐",
        side="affirmative",
        phase="rebuttal",
        segment_label="正方二辩驳论",
        content="2024年某省重点中学引入AI作业批改系统后，学生错题订正率提升近30%。",
        sources=[],
    )

    added = add_message_arguments_to_bank(debate, message)

    assert added == {"affirmative": 0, "negative": 0}
    assert debate.argument_bank["affirmative"] == []


def test_internal_team_discussion_does_not_seed_argument_bank_from_strategy_text() -> None:
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

    added = add_message_arguments_to_bank(debate, message)

    assert added == {"affirmative": 0, "negative": 0}
    assert debate.argument_bank["affirmative"] == []


def test_ai_message_tactics_and_role_assignments_do_not_enter_argument_bank() -> None:
    debate = _debate()
    message = DebateMessage(
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="云汐",
        side="affirmative",
        phase="opening_prep",
        segment_label="正方队内讨论",
        content=(
            "二辩你主要思维训练，找类似可汗学院AI引导解题的案例，强调启发式追问。"
            "四辩你收尾第三个点串成知道漏洞、会想问题、能自己查的闭环。"
            "我这里有一条具体论据，但是先不展开。"
        ),
    )

    added = add_message_arguments_to_bank(debate, message)

    assert added == {"affirmative": 0, "negative": 0}
    assert debate.argument_bank["affirmative"] == []
