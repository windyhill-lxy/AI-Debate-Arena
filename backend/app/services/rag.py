from app.core.config import get_settings
from app.models import Source
from app.services.vector_store import bootstrap_if_empty, ingest_uploaded_text, search, upsert_sources

KNOWLEDGE_BASE = [
    Source(
        id="kb-learning-def",
        title="学习能力的多维度定义",
        excerpt="综合学习能力通常包含知识理解、问题解决、表达协作、自我管理和迁移应用，不能只看考试分数。",
        reliability=0.95,
    ),
    Source(
        id="kb-ai-personalized",
        title="AI 个性化学习优势",
        excerpt="AI 系统可以根据学生答题、提问和薄弱点提供即时反馈，帮助学生更快发现知识漏洞。",
        reliability=0.9,
    ),
    Source(
        id="kb-ai-risk",
        title="AI 学习风险",
        excerpt="过度依赖 AI 可能削弱自主思考、资料辨别和长期专注能力，尤其需要教师与规则引导。",
        reliability=0.88,
    ),
    Source(
        id="kb-edtech-variables",
        title="教育技术的关键变量",
        excerpt="技术能否提升学习效果，往往取决于使用场景、任务设计、反馈质量和学生主动参与程度。",
        reliability=0.86,
    ),
    Source(
        id="kb-debate-scoring",
        title="辩论评分通用维度",
        excerpt="逻辑一致性、事实证据、回应针对性、表达清晰度和礼貌程度是常用评价维度。",
        reliability=0.82,
    ),
]


def init_vector_index() -> None:
    bootstrap_if_empty(KNOWLEDGE_BASE)


def index_debate_topic(topic: str, debate_id: str = "") -> None:
    topic_source = Source(
        id="kb-topic",
        title=f"辩题上下文：{topic[:48]}",
        excerpt=topic,
        reliability=0.75,
    )
    upsert_sources([topic_source], debate_id=debate_id)


def ingest_materials(
    *,
    debate_id: str,
    title: str,
    content: str,
    replace: bool = False,
) -> list[Source]:
    if replace:
        from app.services.vector_store import delete_debate_materials

        delete_debate_materials(debate_id)
    return ingest_uploaded_text(debate_id=debate_id, title=title, content=content)


def retrieve_sources(topic: str, query: str, debate_id: str | None = None) -> list[Source]:
    """轻量向量检索；优先本场辩论上传资料，再合并全局知识库。"""
    settings = get_settings()
    combined = f"{topic}\n{query}"
    ranked = search(combined, top_k=settings.rag_top_k + 4, debate_id=debate_id)
    if not ranked:
        return KNOWLEDGE_BASE[: settings.rag_top_k]

    results: list[Source] = []
    seen: set[str] = set()
    for source, score in ranked:
        if source.id in seen:
            continue
        seen.add(source.id)
        results.append(
            Source(
                id=source.id,
                title=source.title,
                excerpt=source.excerpt,
                url=source.url,
                reliability=min(1.0, source.reliability + score * 0.08),
            )
        )
    return results[: settings.rag_top_k]
