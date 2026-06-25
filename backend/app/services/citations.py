import re

from app.models import Source

_CITATION_RE = re.compile(r"\[([^\]]+)\]")

# 模型常幻觉出的辩题资料编号 → 稳定 id
_CITATION_ALIASES = {
    "kb-topic-x": "kb-topic",
    "topic-x": "kb-topic",
}


def _resolve_source_key(key: str, sources: list[Source]) -> str | None:
    sid = (key or "").strip()
    if not sid:
        return None
    sid = _CITATION_ALIASES.get(sid, sid)
    allowed_ids = {s.id for s in sources}
    if sid in allowed_ids:
        return sid
    for source in sources:
        if source.title and source.title.strip() == sid:
            return source.id
    return None


def sanitize_citations(content: str, sources: list[Source]) -> str:
    """移除正文中未在 sources 列表出现的资料编号，降低幻觉引用。"""
    if not content:
        return content

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        resolved = _resolve_source_key(raw, sources)
        if resolved:
            source = next((s for s in sources if s.id == resolved), None)
            if source and source.title:
                return f"【{source.title}】"
            return match.group(0)
        return ""

    return _CITATION_RE.sub(repl, content)


def has_unverified_citations(content: str, sources: list[Source]) -> bool:
    for raw in _CITATION_RE.findall(content or ""):
        if _resolve_source_key(raw.strip(), sources) is None:
            return True
    return False
