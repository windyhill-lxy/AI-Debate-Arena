from app.models import Source
from app.services.rag import ingest_materials, retrieve_sources
from app.services.vector_store import delete_debate_materials, search


def test_ingest_and_retrieve_debate_scoped() -> None:
    debate_id = "test-debate-001"
    delete_debate_materials(debate_id)
    ingest_materials(
        debate_id=debate_id,
        title="课堂实验",
        content="某校试点显示，AI 辅导组在阅读理解测验中平均分提升 8%。\n\n另一组未使用 AI 的对照班无显著变化。",
    )
    rows = retrieve_sources("青少年 AI 学习", "阅读理解 测验 提升", debate_id=debate_id)
    assert rows
    assert any("阅读理解" in (r.excerpt + r.title) or "AI 辅导" in (r.excerpt + r.title) for r in rows)
    ranked = search("阅读理解 提升", top_k=3, debate_id=debate_id)
    assert ranked
    assert isinstance(ranked[0][0], Source)
