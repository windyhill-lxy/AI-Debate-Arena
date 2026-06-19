from app.models import Source
from app.services.rag import retrieve_sources
from app.services.vector_store import bootstrap_if_empty, embed_text, search, upsert_sources

KNOWLEDGE = [
    Source(id="kb-a", title="AI 学习", excerpt="人工智能个性化反馈帮助发现知识漏洞。", reliability=0.9),
    Source(id="kb-b", title="辩论礼仪", excerpt="逻辑一致性与证据可验证性是评分核心。", reliability=0.85),
]


def test_embed_text_normalized() -> None:
    vec = embed_text("人工智能 辩论")
    norm = sum(v * v for v in vec) ** 0.5
    assert 0.99 <= norm <= 1.01


def test_vector_search_returns_results() -> None:
    bootstrap_if_empty(KNOWLEDGE)
    upsert_sources(
        [
            Source(
                id="kb-topic-x",
                title="辩题",
                excerpt="青少年使用 AI 工具提升学习能力存在争议。",
                reliability=0.8,
            )
        ]
    )
    ranked = search("青少年 AI 学习能力", top_k=2)
    assert ranked
    assert ranked[0][1] > 0


def test_retrieve_sources_uses_vector_index() -> None:
    rows = retrieve_sources("人工智能 青少年 学习", "风险与思考")
    assert rows
    assert all(row.id for row in rows)
