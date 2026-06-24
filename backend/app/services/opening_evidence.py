from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.models import DebateState, Source
from app.services.argument_bank import (
    OPENING_ARGUMENT_TARGET_PER_SIDE,
    add_sources_to_argument_bank_for_side,
    apply_ai_argument_titles,
    argument_count_for_side,
    opening_argument_bank_ready,
)
from app.services.debate_schedule import get_segment
from app.services.llm import DeepSeekError, chat_completion, extract_json_block
from app.services.rag import retrieve_sources

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
ProgressCallback = Callable[[str], Awaitable[None] | None]

OPENING_ARGUMENT_MAX_AI_CALLS_PER_SIDE = 3
OPENING_EVIDENCE_WAIT_SEGMENTS = {
    "aff_opening_discussion",
    "neg_opening_discussion",
    "opening_strategy_lock",
}


@dataclass(frozen=True)
class OpeningEvidenceResult:
    added: dict[str, int]
    sources: list[Source]
    ready: bool


def opening_argument_bank_snapshot(debate: DebateState) -> dict[str, list[dict[str, Any]]]:
    return {
        side: [item.model_dump(mode="json") for item in debate.argument_bank.get(side, [])]
        for side in ("affirmative", "negative")
    }


def current_segment_id(debate: DebateState) -> str:
    segment = get_segment(debate, debate.schedule_index)
    return segment.id if segment else ""


def needs_opening_evidence(debate: DebateState) -> bool:
    if opening_argument_bank_ready(debate):
        return False
    label = debate.segment_label or ""
    segment_id = current_segment_id(debate)
    if debate.phase == "opening_prep" and "真实论据入库" in label:
        return True
    if debate.phase == "opening_prep" and segment_id in OPENING_EVIDENCE_WAIT_SEGMENTS:
        return True
    return debate.phase == "opening_statement"


async def _emit(callback: EventCallback | None, payload: dict[str, Any]) -> None:
    if callback is None:
        return
    result = callback(payload)
    if asyncio.iscoroutine(result):
        await result


async def _progress(callback: ProgressCallback | None, detail: str) -> None:
    if callback is None:
        return
    result = callback(detail)
    if asyncio.iscoroutine(result):
        await result


async def search_real_evidence_with_ai(debate: DebateState, side: str) -> list[Source]:
    side_label = "正方" if side == "affirmative" else "反方"
    try:
        raw = await chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "你是辩论赛事实检索员。请使用可联网检索能力寻找真实事实，不要生成观点口号。"
                        "只返回 JSON，不要 Markdown。每条必须是可核验事实、案例、报告、法规或数据。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"辩题：{debate.topic}\n持方：{side_label}\n"
                        "请返回 6 到 8 条支持本方的真实论据，JSON 格式为："
                        "{\"items\":[{\"title\":\"一行自然语言标题\",\"excerpt\":\"事实摘要，含年份、机构、数据或事件\",\"url\":\"来源链接，可为空\",\"reliability\":0.8}]}"
                        "不要返回辩手分工、价值判断、常识空话或未经证实的虚构案例。"
                    ),
                },
            ],
            temperature=0.25,
            max_tokens=1800,
            debate_id=debate.id,
            operation=f"opening_evidence_web_search_{side}",
        )
        parsed = extract_json_block(raw)
    except (DeepSeekError, Exception):
        return []

    sources: list[Source] = []
    for index, item in enumerate(parsed.get("items") or [], start=1):
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()
        if not title or not excerpt:
            continue
        try:
            reliability = float(item.get("reliability") or 0.78)
        except (TypeError, ValueError):
            reliability = 0.78
        sources.append(
            Source(
                id=f"ai-web-{side}-{index}",
                title=title[:80],
                excerpt=excerpt[:360],
                url=str(item.get("url") or ""),
                reliability=max(0.0, min(1.0, reliability)),
            )
        )
    return sources


async def ensure_opening_argument_bank(
    debate: DebateState,
    *,
    force: bool = False,
    on_event: EventCallback | None = None,
    on_progress: ProgressCallback | None = None,
) -> OpeningEvidenceResult:
    if not force and not needs_opening_evidence(debate):
        return OpeningEvidenceResult(
            added={"affirmative": 0, "negative": 0},
            sources=[],
            ready=opening_argument_bank_ready(debate),
        )
    if opening_argument_bank_ready(debate):
        return OpeningEvidenceResult(
            added={"affirmative": 0, "negative": 0},
            sources=[],
            ready=True,
        )

    await _progress(on_progress, "正在按正反方分别检索真实事实、案例和数据，并写入论据库。")
    total_added = {"affirmative": 0, "negative": 0}
    all_sources: list[Source] = []
    side_queries = {
        "affirmative": "支持正方的真实案例 数据 调查 报告 实验 研究 成效",
        "negative": "支持反方的真实案例 数据 调查 报告 禁令 风险 下降 依赖",
    }
    attempts_by_side = {"affirmative": 0, "negative": 0}

    for attempt_round in range(OPENING_ARGUMENT_MAX_AI_CALLS_PER_SIDE):
        made_progress = False
        for side, query_tail in side_queries.items():
            if argument_count_for_side(debate, side) >= OPENING_ARGUMENT_TARGET_PER_SIDE:
                continue
            attempts_by_side[side] += 1
            attempts = attempts_by_side[side]
            side_label = "正方" if side == "affirmative" else "反方"
            await _progress(on_progress, f"正在检索{side_label}真实事实、案例和数据，并写入公开论据库。")

            query = f"{debate.topic}\n{query_tail}\n只要可核验事实，不要辩论分工或抽象框架。"
            ai_sources = await search_real_evidence_with_ai(debate, side)
            local_sources = retrieve_sources(debate.topic, query, debate_id=debate.id)
            sources = [*ai_sources, *local_sources]
            all_sources.extend(sources)
            added = add_sources_to_argument_bank_for_side(
                debate,
                side,
                sources,
                source_label="AI 检索真实论据入库",
            )
            total_added[side] += added
            made_progress = made_progress or added > 0
            await _emit(
                on_event,
                {
                    "type": "argument_bank_updated",
                    "side": side,
                    "attempt": attempts,
                    "round": attempt_round + 1,
                    "added": added,
                    "affirmative_added": total_added["affirmative"],
                    "negative_added": total_added["negative"],
                    "affirmative_count": argument_count_for_side(debate, "affirmative"),
                    "negative_count": argument_count_for_side(debate, "negative"),
                    "target_per_side": OPENING_ARGUMENT_TARGET_PER_SIDE,
                    "argument_bank": opening_argument_bank_snapshot(debate),
                },
            )
        if not made_progress and all(
            argument_count_for_side(debate, side) >= OPENING_ARGUMENT_TARGET_PER_SIDE
            or attempts_by_side[side] >= OPENING_ARGUMENT_MAX_AI_CALLS_PER_SIDE
            for side in side_queries
        ):
            break

    if total_added["affirmative"] or total_added["negative"]:
        await apply_ai_argument_titles(debate.topic, debate.argument_bank, debate_id=debate.id)

    ready = opening_argument_bank_ready(debate)
    await _emit(
        on_event,
        {
            "type": "argument_bank_seeded",
            "affirmative_added": total_added["affirmative"],
            "negative_added": total_added["negative"],
            "affirmative_count": argument_count_for_side(debate, "affirmative"),
            "negative_count": argument_count_for_side(debate, "negative"),
            "target_per_side": OPENING_ARGUMENT_TARGET_PER_SIDE,
            "argument_bank": opening_argument_bank_snapshot(debate),
            "ready": ready,
        },
    )
    return OpeningEvidenceResult(added=total_added, sources=all_sources, ready=ready)
