from __future__ import annotations

import re

from app.models import ArgumentBankItem, DebateState, Source


SIDE_PREFIX = {"affirmative": "AFF", "negative": "NEG"}
TITLE_STOPWORDS = (
    "能够",
    "可以",
    "可能",
    "导致",
    "让辩手",
    "让学生",
    "我方认为",
    "对方认为",
    "给出",
    "会",
    "能",
    "将",
)


def short_argument_title(claim: str) -> str:
    text = re.split(r"[，。；;：:\n]", claim or "", maxsplit=1)[0]
    text = re.sub(r"\s+", "", text)
    for word in TITLE_STOPWORDS:
        text = text.replace(word, "")
    unverifiable_case = re.match(r"(.{1,6}).*未经证实.*案例", text)
    if unverifiable_case:
        return f"{unverifiable_case.group(1)}案例未经证实"[:14]
    text = text.strip("，。；;：:、 ")
    return text[:14] or "核心论据"


def add_argument_items(debate: DebateState, side: str, items: list[ArgumentBankItem]) -> None:
    if side not in {"affirmative", "negative"}:
        return
    existing = {item.id for item in debate.argument_bank.get(side, [])}
    bucket = debate.argument_bank.setdefault(side, [])
    for item in items:
        if item.id not in existing and item.side == side:
            bucket.append(item)
            existing.add(item.id)
    debate.argument_bank_locked = True


def build_argument_bank_items(
    claims: dict[str, list[str]],
    *,
    source: str = "AI 预生成论据库",
) -> dict[str, list[ArgumentBankItem]]:
    bank: dict[str, list[ArgumentBankItem]] = {"affirmative": [], "negative": []}
    for side in ("affirmative", "negative"):
        prefix = SIDE_PREFIX[side]
        for index, claim in enumerate(claims.get(side, []), start=1):
            text = re.sub(r"\s+", " ", (claim or "")).strip()
            if not text:
                continue
            bank[side].append(
                ArgumentBankItem(
                    id=f"{prefix}-{index}",
                    side=side,  # type: ignore[arg-type]
                    title=short_argument_title(text),
                    claim=text,
                    source=source,
                )
            )
    return bank


def _claim_from_source(topic: str, source: Source, side: str) -> str:
    excerpt = re.sub(r"\s+", " ", (source.excerpt or source.title or "").strip())
    if not excerpt:
        excerpt = f"围绕{topic}的可检索资料可作为本方论证支撑。"
    if side == "affirmative":
        return f"{excerpt} 这支持正方关于辩题具有积极效果或可控价值的论证。"
    return f"{excerpt} 这支持反方关于辩题存在风险、边界或替代方案的论证。"


def _source_relevant_to_side(text: str, side: str) -> bool:
    positive = ("提升", "帮助", "促进", "增强", "降低成本", "即时反馈", "效率", "积极", "可控")
    negative = ("风险", "依赖", "削弱", "错误", "不可靠", "隐私", "替代", "负面", "未经证实")
    terms = positive if side == "affirmative" else negative
    return any(term in text for term in terms)


def build_argument_bank_from_sources(topic: str, sources: list[Source]) -> dict[str, list[ArgumentBankItem]]:
    claims: dict[str, list[str]] = {"affirmative": [], "negative": []}
    for source in sources:
        text = f"{source.title} {source.excerpt}"
        for side in ("affirmative", "negative"):
            if _source_relevant_to_side(text, side) or len(claims[side]) == 0:
                claims[side].append(_claim_from_source(topic, source, side))
        if len(claims["affirmative"]) >= 3 and len(claims["negative"]) >= 3:
            break
    return build_argument_bank_items(claims, source="RAG 资料入库")


def argument_ids_for_side(debate: DebateState, side: str) -> set[str]:
    return {item.id for item in debate.argument_bank.get(side, [])}


def referenced_argument_ids(text: str) -> set[str]:
    return set(re.findall(r"\b(?:AFF|NEG)-\d+\b", text or "", flags=re.IGNORECASE))


def enforce_argument_citations(debate: DebateState, side: str, content: str) -> tuple[bool, str]:
    if side not in {"affirmative", "negative"}:
        return True, ""
    if not debate.argument_bank_locked:
        return True, ""
    ids = referenced_argument_ids(content)
    allowed = argument_ids_for_side(debate, side)
    if ids and ids.issubset(allowed):
        return True, ""
    if not allowed:
        return True, ""
    return False, "知识性论证必须引用本方论据库中的论据 ID，避免常识性或 AI 味泛化输出。"
