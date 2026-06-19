from app.api.debates import _export_markdown
from app.models import (
    DebateMessage,
    DebateMode,
    DebateState,
    DebateTiming,
    DebateVisibility,
    Source,
    default_agents,
    workflow_template,
)
from app.services.rag import KNOWLEDGE_BASE, retrieve_sources


def test_knowledge_base_has_stable_ids() -> None:
    ids = [s.id for s in KNOWLEDGE_BASE]
    assert len(ids) == len(set(ids))
    assert "kb-ai-risk" in ids


def test_retrieve_sources_returns_ranked_with_ids() -> None:
    rows = retrieve_sources("人工智能 青少年 学习", "风险与思考能力")
    assert rows
    assert all(getattr(r, "id", "") for r in rows)


def test_export_markdown_includes_messages_and_sources() -> None:
    agents = default_agents()
    debate = DebateState(
        topic="测试辩题",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=agents,
        workflow=workflow_template(),
    )
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="云汐",
            side="affirmative",
            content="**主席好**，这是测试发言。",
            phase="opening_statement",
            segment_label="正方一辩立论",
            sources=[
                Source(
                    id="kb-test",
                    title="测试资料",
                    excerpt="用于导出单元测试的摘要。",
                    reliability=0.9,
                )
            ],
        )
    )
    md = _export_markdown(debate)
    assert "测试辩题" in md
    assert "云汐" in md
    assert "`[kb-test]`" in md


def test_export_pdf_returns_pdf_bytes() -> None:
    from app.services.export_pdf import markdown_to_pdf_bytes

    pdf = markdown_to_pdf_bytes("# 导出测试\n\n- 条目一\n\n正文段落。")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
