from __future__ import annotations

import re

from app.models import ArgumentBankItem, DebateMessage, DebateState, Source


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
MAX_TITLE_LEN = 18


def short_argument_title(claim: str) -> str:
    quoted = re.search(r"[“\"《]([^”\"》]{6,80})[”\"》]", claim or "")
    if quoted:
        claim = quoted.group(1)
    if "AI作业批改" in (claim or "") and "订正率" in (claim or ""):
        return "AI作业批改订正率提升"
    if "韩国AI作业禁令" in (claim or ""):
        return "韩国AI作业禁令"
    if "AI" in (claim or "") and "个性化反馈" in (claim or "") and "知识漏洞" in (claim or ""):
        return "AI个性化反馈发现漏洞"
    text = re.split(r"[，。；;：:\n]", claim or "", maxsplit=1)[0]
    text = re.sub(r"^.*?(?:例子上用|例如|案例是|调研是)", "", text)
    text = re.sub(r"^我作为[一二三四]辩.*?(?=AI|人工智能|韩国|OECD|20\d{2}年)", "", text)
    text = re.sub(r"\s+", "", text)
    for word in TITLE_STOPWORDS:
        text = text.replace(word, "")
    unverifiable_case = re.match(r"(.{1,6}).*未经证实.*案例", text)
    if unverifiable_case:
        return f"{unverifiable_case.group(1)}案例未经证实"[:14]
    text = text.strip("，。；;：:、 ")
    return text[:MAX_TITLE_LEN] or "核心论据"


def _normalise_key(text: str) -> str:
    text = re.sub(r"[【】\[\]\s，。；;：:、,.!?！？（）()《》“”\"']", "", text or "")
    return text[:80]


def _argument_key(item: ArgumentBankItem) -> str:
    return _normalise_key(item.title or item.claim)


def _source_display_title(source: Source) -> str:
    title = source.title or source.excerpt or "资料论据"
    title = re.sub(r"\s*[·\-_]\s*片段\s*\d+\s*$", "", title).strip()
    excerpt = re.sub(r"\s+", " ", source.excerpt or "").strip()
    generic_title = (
        not title
        or len(re.sub(r"\s+", "", title)) <= 6
        or any(term in title for term in ("资料", "材料", "AI学习", "学习", "调研", "研究"))
    )
    has_concrete_evidence = bool(re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%|禁令|调查|调研|报告|数据显示", excerpt))
    if generic_title or has_concrete_evidence:
        return short_argument_title(f"{title} {excerpt}".strip())
    return short_argument_title(title)


def _is_generic_system_source(source: Source) -> bool:
    sid = source.id or ""
    title = source.title or ""
    text = f"{title} {source.excerpt or ''}"
    if sid in {"kb-topic", "kb-debate-scoring", "kb-learning-def"}:
        return True
    generic_terms = ("辩题上下文", "辩题", "辩论礼仪", "评分", "评分核心", "通用维度", "多维度定义")
    if any(term in title for term in generic_terms):
        return True
    if "是否" in text and len(source.excerpt or "") < 40:
        return True
    return False


def _next_argument_id(debate: DebateState, side: str) -> str:
    prefix = SIDE_PREFIX[side]
    indexes: list[int] = []
    for item in debate.argument_bank.get(side, []):
        match = re.fullmatch(rf"{prefix}-(\d+)", item.id or "", flags=re.IGNORECASE)
        if match:
            indexes.append(int(match.group(1)))
    return f"{prefix}-{(max(indexes) if indexes else 0) + 1}"


def add_argument_items(debate: DebateState, side: str, items: list[ArgumentBankItem]) -> None:
    if side not in {"affirmative", "negative"}:
        return
    prefix = SIDE_PREFIX[side]
    existing_ids = {item.id for item in debate.argument_bank.get(side, [])}
    existing_keys = {_argument_key(item) for item in debate.argument_bank.get(side, [])}
    bucket = debate.argument_bank.setdefault(side, [])
    for item in items:
        if item.side != side:
            continue
        key = _argument_key(item)
        if key and key in existing_keys:
            continue
        item_id = item.id if re.fullmatch(rf"{prefix}-\d+", item.id or "", flags=re.IGNORECASE) else ""
        if not item_id or item_id in existing_ids:
            item_id = _next_argument_id(debate, side)
        normalized = item.model_copy(
            update={
                "id": item_id,
                "title": (item.title or short_argument_title(item.claim))[:MAX_TITLE_LEN],
                "claim": re.sub(r"\s+", " ", item.claim or "").strip(),
            }
        )
        bucket.append(normalized)
        existing_ids.add(normalized.id)
        existing_keys.add(_argument_key(normalized))
    if debate.argument_bank.get("affirmative") or debate.argument_bank.get("negative"):
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
    positive = ("提升", "帮助", "促进", "增强", "降低成本", "即时反馈", "效率", "积极", "可控", "发现知识漏洞", "复盘")
    negative = ("风险", "依赖", "削弱", "错误", "不可靠", "隐私", "替代", "负面", "未经证实", "禁令", "禁止", "限制", "担心", "下降")
    terms = positive if side == "affirmative" else negative
    return any(term in text for term in terms)


def _side_score(text: str, side: str) -> int:
    positive = ("提升", "帮助", "促进", "增强", "即时反馈", "效率", "积极", "可控", "发现知识漏洞", "复盘", "订正率", "个性化反馈")
    negative = ("风险", "依赖", "削弱", "错误", "不可靠", "隐私", "替代", "负面", "未经证实", "禁令", "禁止", "限制", "担心", "下降")
    terms = positive if side == "affirmative" else negative
    return sum(1 for term in terms if term in text)


def _source_sides(text: str) -> list[str]:
    aff_score = _side_score(text, "affirmative")
    neg_score = _side_score(text, "negative")
    strong_negative = any(term in text for term in ("禁令", "禁止", "限制", "削弱", "下降", "替代", "依赖", "风险"))
    strong_positive = any(term in text for term in ("订正率", "提升近", "提升", "帮助", "促进", "发现知识漏洞"))
    if strong_negative and neg_score >= aff_score:
        return ["negative"]
    if strong_positive and aff_score >= neg_score:
        return ["affirmative"]
    if aff_score > neg_score:
        return ["affirmative"]
    if neg_score > aff_score:
        return ["negative"]
    return []


def build_argument_bank_from_sources(topic: str, sources: list[Source]) -> dict[str, list[ArgumentBankItem]]:
    bank: dict[str, list[ArgumentBankItem]] = {"affirmative": [], "negative": []}
    counters = {"affirmative": 0, "negative": 0}
    for source in sources:
        if _is_generic_system_source(source):
            continue
        text = f"{source.title} {source.excerpt}"
        sides = _source_sides(text)
        for side in sides:
            counters[side] += 1
            bank[side].append(
                ArgumentBankItem(
                    id=f"{SIDE_PREFIX[side]}-{counters[side]}",
                    side=side,  # type: ignore[arg-type]
                    title=_source_display_title(source),
                    claim=_claim_from_source(topic, source, side),
                    source="RAG 资料入库",
                )
            )
    return bank


def add_sources_to_argument_bank(debate: DebateState, sources: list[Source]) -> dict[str, int]:
    before = {side: len(debate.argument_bank.get(side, [])) for side in ("affirmative", "negative")}
    bank = build_argument_bank_from_sources(debate.topic, sources)
    add_argument_items(debate, "affirmative", bank["affirmative"])
    add_argument_items(debate, "negative", bank["negative"])
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


def _extract_claims_from_message(content: str) -> list[str]:
    text = re.sub(r"\s+", " ", content or "").strip()
    if not text:
        return []
    claims: list[str] = []
    markers = (
        "研究",
        "报告",
        "数据显示",
        "调查",
        "案例",
        "禁令",
        "限制",
        "禁止",
        "说明",
        "表明",
        "证明",
        "显示",
        "OECD",
    )
    quoted_claims = re.findall(r"[“\"《]([^”\"》]{8,120})[”\"》]", text)
    for quoted in quoted_claims:
        if any(marker in quoted for marker in markers) or re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%", quoted):
            claims.append(quoted.strip())
    for sentence in re.split(r"(?<=[。！？!?])", text):
        sentence = sentence.strip(" ，。；;")
        if len(sentence) < 18:
            continue
        if any(marker in sentence for marker in markers) or re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%", sentence):
            claims.append(sentence)
    deduped: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        key = _normalise_key(claim)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped[:4]


def add_message_arguments_to_bank(debate: DebateState, message: DebateMessage) -> dict[str, int]:
    if message.side not in {"affirmative", "negative"}:
        return {"affirmative": 0, "negative": 0}
    before = {side: len(debate.argument_bank.get(side, [])) for side in ("affirmative", "negative")}
    if message.sources:
        add_sources_to_argument_bank(debate, message.sources)
    claims = _extract_claims_from_message(message.content)
    items = [
        ArgumentBankItem(
            id=f"{SIDE_PREFIX[message.side]}-{index}",
            side=message.side,  # type: ignore[arg-type]
            title=short_argument_title(claim),
            claim=claim,
            source=f"AI 发言入库 · {message.speaker_name}",
        )
        for index, claim in enumerate(claims, start=1)
    ]
    add_argument_items(debate, message.side, items)
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


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
