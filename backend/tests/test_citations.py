from app.models import Source
from app.services.citations import has_unverified_citations, sanitize_citations


def test_sanitize_removes_unknown_ids() -> None:
    sources = [Source(id="kb-1", title="A", excerpt="x")]
    text = "见资料[kb-1]与[kb-fake]。"
    cleaned = sanitize_citations(text, sources)
    assert "【A】" in cleaned
    assert "[kb-fake]" not in cleaned
    assert "【" in cleaned


def test_sanitize_maps_topic_alias_and_title() -> None:
    sources = [Source(id="kb-topic", title="辩题上下文：AI学习", excerpt="辩题摘要")]
    text = "背景见[kb-topic-x]与【辩题上下文：AI学习】。"
    cleaned = sanitize_citations(text, sources)
    assert cleaned.count("【辩题上下文：AI学习】") == 2


def test_has_unverified_citations() -> None:
    sources = [Source(id="kb-1", title="A", excerpt="x")]
    assert has_unverified_citations("引用[kb-2]", sources)
    assert not has_unverified_citations("引用[kb-1]", sources)
