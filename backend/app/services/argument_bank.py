from __future__ import annotations

import json
import re

from app.models import ArgumentBankItem, DebateMessage, DebateState, Source
from app.services.llm import chat_completion, extract_json_block
from app.services.message_visibility import is_internal_message


SIDE_PREFIX = {"affirmative": "AFF", "negative": "NEG"}
KB_CITATION_PATTERN = re.compile(r"\s*[\[【]\s*kb-[^\]】]+\s*[\]】]", re.IGNORECASE)
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
OPENING_ARGUMENT_TARGET_PER_SIDE = 10
FACT_PATTERN = re.compile(
    r"\d{4}\s*年|\d+[\.\d]*\s*%|百分之[一二三四五六七八九十百千万零〇两]+|"
    r"(大学|学院|中学|小学|教育部|OECD|联合国|法院|政府|平台|公司|机构|实验|调查|研究|报告|论文|报道|禁令|规定|法案|通知)"
)
REJECT_PATTERN = re.compile(
    r"我作为|我负责|我来|你主要|你收尾|二辩|三辩|四辩|一辩先|认同框架|立论框架|"
    r"找类似|强化案例|我这里有|具体论据|先不展开|重点讲|主讲|串成|闭环"
)


def short_argument_title(claim: str) -> str:
    quoted = re.search(r"[“\"《]([^”\"》]{6,80})[”\"》]", claim or "")
    if quoted:
        claim = quoted.group(1)
    claim = re.sub(r"来源《[^》]+》记录[:：]\s*", "", claim or "")
    claim = re.sub(r"\s+", "", claim)
    if "AI作业批改" in (claim or "") and "订正率" in (claim or ""):
        return "AI作业批改订正率提升"
    if "韩国AI作业禁令" in (claim or ""):
        return "韩国AI作业禁令"
    if "AI自适应学习平台" in (claim or "") and ("数学测评" in (claim or "") or "测评" in (claim or "")):
        return "AI自适应学习平台测评提升"
    if "AI解题" in (claim or "") and "自主解题" in (claim or "") and "下降" in (claim or ""):
        return "AI解题后自主解题下降"
    if "AI" in (claim or "") and "个性化反馈" in (claim or "") and "知识漏洞" in (claim or ""):
        return "AI个性化反馈发现漏洞"
    if "AI口语陪练" in (claim or "") and "练习频次" in (claim or "") and "提升" in (claim or ""):
        return "AI口语陪练频次提升"
    if "AI" in (claim or "") and "教师" in (claim or "") and "面批" in (claim or ""):
        return "AI批改释放教师面批"
    lead_pattern = (
        r"^\d{4}年[^，。；;：:]*?(?:显示|表明|发现|指出|报道|发布|调查|报告|提醒|限制|禁止)"
        r"[，。；;：:]?"
    )
    claim = re.sub(lead_pattern, "", claim or "")
    claim = re.sub(
        r"^\d{4}年(?:一项)?(?:针对[^，。；;：:]{0,24}的)?(?:调查|研究|实验|报告)(?:显示|表明|发现|指出)?[，。；;：:]?",
        "",
        claim or "",
    )
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
    return _normalise_key(item.claim or item.title)


def _is_factual_evidence(text: str, *, allow_rag_source: bool = False) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    if REJECT_PATTERN.search(compact):
        return False
    if allow_rag_source and FACT_PATTERN.search(compact):
        return True
    if not FACT_PATTERN.search(compact):
        return False
    has_outcome = any(
        term in compact
        for term in (
            "提升",
            "下降",
            "增加",
            "减少",
            "限制",
            "禁止",
            "发现",
            "显示",
            "指出",
            "发布",
            "调查",
            "实验",
            "报道",
            "准确率",
            "订正率",
            "自主解题",
        )
    )
    return has_outcome


def _source_display_title(source: Source) -> str:
    title = source.title or source.excerpt or "资料论据"
    title = re.sub(r"\s*[·\-_]\s*片段\s*\d+\s*$", "", title).strip()
    excerpt = re.sub(r"\s+", " ", source.excerpt or "").strip()
    generic_title = (
        not title
        or len(re.sub(r"\s+", "", title)) <= 6
        or any(term in title for term in ("资料", "材料", "AI学习", "学习", "调研", "研究", "调查", "观察", "风险", "影响"))
    )
    has_concrete_evidence = bool(re.search(r"\d{4}\s*年|\d+[\.\d]*\s*%|禁令|调查|调研|报告|数据显示", excerpt))
    if generic_title or has_concrete_evidence:
        if not generic_title:
            return short_argument_title(title)
        return short_argument_title(excerpt or title)
    return short_argument_title(title)


def _clean_ai_argument_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title or "").strip()
    text = re.sub(r"^[-*\d.、\s]*(?:标题|论据标题|title)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\[【]\s*(?:AFF|NEG)-\d+\s*[\]】]", "", text, flags=re.IGNORECASE)
    text = text.strip("`'\"“”‘’《》【】[]（）() ，。；;：:、")
    text = re.sub(r"\s+", "", text)
    return text[:MAX_TITLE_LEN]


def _parse_ai_title_map(raw: str, allowed_ids: set[str]) -> dict[str, str]:
    try:
        parsed = extract_json_block(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    rows = parsed.get("titles") or parsed.get("items") or parsed.get("arguments") or []
    title_map: dict[str, str] = {}
    if not isinstance(rows, list):
        return title_map
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(
            row.get("id")
            or row.get("argument_id")
            or row.get("论据ID")
            or row.get("论据编号")
            or ""
        ).upper()
        if item_id not in allowed_ids:
            continue
        title = _clean_ai_argument_title(
            str(row.get("title") or row.get("标题") or row.get("summary_title") or "")
        )
        if title:
            title_map[item_id] = title
    return title_map


async def apply_ai_argument_titles(
    topic: str,
    bank: dict[str, list[ArgumentBankItem]],
    *,
    debate_id: str | None = None,
) -> None:
    candidates = [
        item
        for side in ("affirmative", "negative")
        for item in bank.get(side, [])
        if item.id and item.claim
    ]
    if not candidates:
        return
    allowed_ids = {item.id.upper() for item in candidates}
    payload = [
        {
            "id": item.id,
            "side": "正方" if item.side == "affirmative" else "反方",
            "claim": item.claim,
        }
        for item in candidates
    ]
    try:
        raw = await chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "你是辩论论据库标题编辑。只返回 JSON，不要 Markdown。"
                        "请为每条论据提炼短标题，标题必须概括论据核心事实或数据，"
                        "不得截取原文前几个字，不得写成观点口号，不得包含论据编号。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"辩题：{topic}\n"
                        "请为下列论据分别生成 8 到 16 个汉字左右的标题。"
                        "输出格式：{\"titles\":[{\"id\":\"AFF-1\",\"title\":\"AI反馈提升订正率\"}]}\n"
                        f"论据：{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=min(1600, 200 + len(candidates) * 80),
            debate_id=debate_id,
            operation="argument_bank_title_summary",
        )
    except Exception:
        return
    title_map = _parse_ai_title_map(raw, allowed_ids)
    for item in candidates:
        title = title_map.get(item.id.upper())
        if title:
            item.title = title


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
        accepted = 0
        for claim in claims.get(side, []):
            text = re.sub(r"\s+", " ", (claim or "")).strip()
            if not text or not _is_factual_evidence(text):
                continue
            accepted += 1
            bank[side].append(
                ArgumentBankItem(
                    id=f"{prefix}-{accepted}",
                    side=side,  # type: ignore[arg-type]
                    title=short_argument_title(text),
                    claim=text,
                    source=source,
                )
            )
    return bank


def _claim_from_source(topic: str, source: Source, side: str) -> str:
    title = re.sub(r"\s+", " ", (source.title or "可核验资料").strip())
    excerpt = re.sub(r"\s+", " ", (source.excerpt or source.title or "").strip())
    if not excerpt:
        excerpt = f"围绕{topic}的可检索资料可作为本方论证支撑。"
    fact = f"来源《{title}》记录：{excerpt}"
    if source.url:
        fact = f"{fact} 来源链接：{source.url}"
    if side == "affirmative":
        return f"{fact} 这支持正方关于辩题具有积极效果或可控价值的论证。"
    return f"{fact} 这支持反方关于辩题存在风险、边界或替代方案的论证。"


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


def build_argument_bank_from_sources(
    topic: str,
    sources: list[Source],
    *,
    target_side: str | None = None,
    source_label: str = "RAG 资料入库",
) -> dict[str, list[ArgumentBankItem]]:
    bank: dict[str, list[ArgumentBankItem]] = {"affirmative": [], "negative": []}
    counters = {"affirmative": 0, "negative": 0}
    for source in sources:
        if _is_generic_system_source(source):
            continue
        text = f"{source.title} {source.excerpt}"
        if not _is_factual_evidence(text, allow_rag_source=True):
            continue
        sides = _source_sides(text)
        if target_side in {"affirmative", "negative"}:
            sides = [target_side] if target_side in sides or _source_relevant_to_side(text, target_side) else []
        for side in sides:
            counters[side] += 1
            bank[side].append(
                ArgumentBankItem(
                    id=f"{SIDE_PREFIX[side]}-{counters[side]}",
                    side=side,  # type: ignore[arg-type]
                    title=_source_display_title(source),
                    claim=_claim_from_source(topic, source, side),
                    source=source_label,
                )
            )
    return bank


def add_sources_to_argument_bank(debate: DebateState, sources: list[Source]) -> dict[str, int]:
    before = {side: len(debate.argument_bank.get(side, [])) for side in ("affirmative", "negative")}
    bank = build_argument_bank_from_sources(debate.topic, sources)
    add_argument_items(debate, "affirmative", bank["affirmative"])
    add_argument_items(debate, "negative", bank["negative"])
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


async def add_sources_to_argument_bank_with_ai_titles(debate: DebateState, sources: list[Source]) -> dict[str, int]:
    before = {side: len(debate.argument_bank.get(side, [])) for side in ("affirmative", "negative")}
    bank = build_argument_bank_from_sources(debate.topic, sources)
    await apply_ai_argument_titles(debate.topic, bank, debate_id=debate.id)
    add_argument_items(debate, "affirmative", bank["affirmative"])
    add_argument_items(debate, "negative", bank["negative"])
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


def add_sources_to_argument_bank_for_side(
    debate: DebateState,
    side: str,
    sources: list[Source],
    *,
    source_label: str = "AI 检索真实论据入库",
) -> int:
    if side not in {"affirmative", "negative"}:
        return 0
    before = len(debate.argument_bank.get(side, []))
    bank = build_argument_bank_from_sources(
        debate.topic,
        sources,
        target_side=side,
        source_label=source_label,
    )
    add_argument_items(debate, side, bank[side])
    return len(debate.argument_bank.get(side, [])) - before


async def add_sources_to_argument_bank_for_side_with_ai_titles(
    debate: DebateState,
    side: str,
    sources: list[Source],
    *,
    source_label: str = "AI 检索真实论据入库",
) -> int:
    if side not in {"affirmative", "negative"}:
        return 0
    before = len(debate.argument_bank.get(side, []))
    bank = build_argument_bank_from_sources(
        debate.topic,
        sources,
        target_side=side,
        source_label=source_label,
    )
    await apply_ai_argument_titles(debate.topic, bank, debate_id=debate.id)
    add_argument_items(debate, side, bank[side])
    return len(debate.argument_bank.get(side, [])) - before


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
        if _is_factual_evidence(quoted) and (any(marker in quoted for marker in markers) or FACT_PATTERN.search(quoted)):
            claims.append(quoted.strip())
    for sentence in re.split(r"(?<=[。！？!?])", text):
        sentence = sentence.strip(" ，。；;")
        if len(sentence) < 18:
            continue
        if _is_factual_evidence(sentence) and (any(marker in sentence for marker in markers) or FACT_PATTERN.search(sentence)):
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
    if is_internal_message(message):
        return {"affirmative": 0, "negative": 0}
    if message.sources:
        add_sources_to_argument_bank(debate, message.sources)
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


async def add_message_arguments_to_bank_with_ai_titles(debate: DebateState, message: DebateMessage) -> dict[str, int]:
    if message.side not in {"affirmative", "negative"}:
        return {"affirmative": 0, "negative": 0}
    before = {side: len(debate.argument_bank.get(side, [])) for side in ("affirmative", "negative")}
    if is_internal_message(message):
        return {"affirmative": 0, "negative": 0}
    if message.sources:
        await add_sources_to_argument_bank_with_ai_titles(debate, message.sources)
    return {side: len(debate.argument_bank.get(side, [])) - before[side] for side in ("affirmative", "negative")}


def argument_ids_for_side(debate: DebateState, side: str) -> set[str]:
    return {item.id for item in debate.argument_bank.get(side, [])}


def argument_count_for_side(debate: DebateState, side: str) -> int:
    if side not in {"affirmative", "negative"}:
        return 0
    return len(debate.argument_bank.get(side, []))


def opening_argument_bank_ready(debate: DebateState) -> bool:
    return all(
        argument_count_for_side(debate, side) >= OPENING_ARGUMENT_TARGET_PER_SIDE
        for side in ("affirmative", "negative")
    )


def referenced_argument_ids(text: str) -> set[str]:
    return {match.upper() for match in re.findall(r"(?<![A-Za-z0-9])(?:AFF|NEG)-\d+(?![A-Za-z0-9])", text or "", flags=re.IGNORECASE)}


def primary_argument_id_for_side(debate: DebateState, side: str, position: int = 1) -> str:
    if side not in {"affirmative", "negative"}:
        return ""
    items = [item for item in debate.argument_bank.get(side, []) if item.id]
    if items:
        return items[min(max(position - 1, 0), len(items) - 1)].id
    return f"{SIDE_PREFIX[side]}-{max(position, 1)}"


def normalize_argument_citations(text: str, debate: DebateState, side: str, *, position: int = 1) -> str:
    if not text:
        return text
    cleaned = KB_CITATION_PATTERN.sub("", text)
    if side not in {"affirmative", "negative"}:
        return cleaned.strip()
    allowed = argument_ids_for_side(debate, side)
    ids = referenced_argument_ids(cleaned)
    if allowed:
        cleaned = re.sub(
            r"[\[【]\s*((?:AFF|NEG)-\d+)\s*[\]】]",
            lambda match: match.group(0) if match.group(1).upper() in allowed else "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?<![A-Za-z0-9])(?:AFF|NEG)-\d+(?![A-Za-z0-9])",
            lambda match: match.group(0).upper() if match.group(0).upper() in allowed else "",
            cleaned,
            flags=re.IGNORECASE,
        )
        ids = referenced_argument_ids(cleaned)
    if ids:
        return re.sub(r"\s{2,}", " ", cleaned).strip()
    fallback_id = primary_argument_id_for_side(debate, side, position)
    if not fallback_id:
        return re.sub(r"\s{2,}", " ", cleaned).strip()
    stripped = cleaned.rstrip()
    suffix = f" [{fallback_id}]"
    if stripped.endswith(("。", "！", "？", ".", "!", "?")):
        return f"{stripped}{suffix}"
    return f"{stripped}{suffix}。"


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
