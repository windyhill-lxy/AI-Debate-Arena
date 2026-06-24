import asyncio
import json
import logging
import re
from uuid import uuid4

from app.core.time_utils import utc_now

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from app.core.rate_limit import enforce_create_room_limit, enforce_write_limit
from app.db.mongo import get_debate, list_debates, save_debate
from app.db.redis_cache import cache_publish, cache_set
from app.models import (
    AssistRequest,
    DebateCreate,
    DebateImport,
    DebateMessage,
    DebateMode,
    DebateState,
    DebateVisibility,
    OpeningTrainingAutoImprove,
    OpeningTrainingAnalyze,
    OpeningTrainingPolish,
    MaterialUpload,
    OnlineParticipant,
    ParticipantJoin,
    UserDraftUpdate,
    UserMessageCreate,
    build_schedule_status,
    default_agents,
    workflow_template,
)
from app.services.auto_runner import resume_auto, start_auto, stop_auto
from app.services.asr import ASRError, recognize_speech
from app.services.argument_bank import (
    add_argument_items,
    add_sources_to_argument_bank_with_ai_titles,
    enforce_argument_citations,
    opening_argument_bank_ready,
)
from app.services.changelog import append_changelog, ensure_project_index
from app.services.confidence_monitor_manager import manager as confidence_manager
from app.services.debate_mode import (
    debate_user_position,
    debate_user_side,
    is_user_task_assign_segment,
    is_user_team_discussion_segment,
    needs_user_turn,
    opening_team_discussion_ready,
    participant_speaker_id,
    user_side_for_mode,
)
from app.services.speech_timeout import clear_user_wait, mark_user_wait_start
from app.services.debate_schedule import init_schedule
from app.services.assist import generate_assist, generate_assist_stream_events
from app.services.draft_assist import generate_draft, generate_draft_stream_events
from app.services.export_pdf import markdown_to_pdf_bytes
from app.services.host_control_auth import issue_host_token, verify_host_token
from app.services.online_session import create_session as create_online_session_id, get_session, link_session
from app.services.llm_usage import get_debate_llm_stats
from app.services.user_speech_judge import UserSpeechReview, review_user_speech
from app.services.rag import index_debate_topic, ingest_materials, retrieve_sources
from app.services.runtime_settings import RuntimeSettings, apply_runtime_settings, load_runtime_settings, mask_key, merged_api_keys
from app.services.schedule_config import list_schedule_templates_meta
from app.services.training import analyze_opening_draft, auto_improve_opening_draft, auto_improve_opening_draft_events, polish_opening_draft
from app.services import presence
from app.services.realtime import manager
from app.services.ops_events import append_ops_event
from app.services.opening_evidence_warmup import cancel_opening_evidence_warmup, start_opening_evidence_warmup
from app.services.user_turn_flow import accept_user_message, speaker_id_for_user_message
from app.workflow.debate_graph import debate_graph

router = APIRouter(prefix="/api/debates", tags=["debates"])
logger = logging.getLogger(__name__)


def warm_opening_evidence(debate: DebateState) -> None:
    start_opening_evidence_warmup(
        debate.id,
        debate.topic,
        persist_and_broadcast=_persist_and_broadcast,
        on_ready=resume_auto,
    )


async def _index_debate_materials_background(
    topic: str,
    debate_id: str,
    materials: list,
) -> None:
    def _sync_index() -> None:
        index_debate_topic(topic, debate_id)
        for material in materials:
            if material.content.strip():
                ingest_materials(
                    debate_id=debate_id,
                    title=material.title or "辩题参考资料",
                    content=material.content,
                )

    try:
        await asyncio.to_thread(_sync_index)
    except Exception:
        logger.exception("background index failed for debate %s", debate_id)


def _state_from_doc(doc: dict) -> DebateState:
    return DebateState.model_validate(doc)


def _visibility_for_created_room(payload: DebateCreate) -> DebateVisibility:
    if payload.mode == DebateMode.ai_autonomous:
        return DebateVisibility.all_visible
    if payload.visibility in {DebateVisibility.god, DebateVisibility.all_visible}:
        return DebateVisibility.all_visible
    return DebateVisibility.own_side_only


def _lock_initial_rules(debate: DebateState) -> None:
    debate.visibility_locked = True
    debate.timing_locked = True
    debate.rules_locked_at = utc_now()


def _find_participant(debate: DebateState, participant_id: str | None) -> OnlineParticipant | None:
    if not participant_id:
        return None
    return next((p for p in debate.participants if p.id == participant_id), None)


def _viewer_side_for_state(
    debate: DebateState,
    *,
    viewer_side: str | None = None,
    participant_id: str | None = None,
) -> str | None:
    if viewer_side in {"affirmative", "negative"}:
        return viewer_side
    participant = _find_participant(debate, participant_id)
    if participant and participant.side in {"affirmative", "negative"}:
        return participant.side
    if debate.mode in {DebateMode.user_affirmative, DebateMode.user_negative}:
        return debate_user_side(debate)
    return None


from app.services.viewer_payload import (
    debate_payload_for_viewer as _debate_payload_for_viewer,
    normalize_viewer_mode,
    streaming_event_visible,
)


async def _broadcast_debate_event(debate_id: str, debate: DebateState, event: dict) -> None:
    await manager.broadcast_filtered(
        debate_id,
        event,
        lambda payload, connection: streaming_event_visible(
            debate,
            payload,
            viewer_side=_viewer_side_for_state(
                debate,
                viewer_side=connection.get("viewer_side"),
                participant_id=connection.get("participant_id"),
            ),
            viewer_mode=connection.get("viewer_mode"),
        ),
    )


def _payload_for_viewer_request(
    debate: DebateState,
    *,
    viewer_side: str | None = None,
    participant_id: str | None = None,
    viewer_mode: str | None = None,
) -> dict:
    return _debate_payload_for_viewer(
        debate,
        viewer_side=viewer_side,
        participant=_find_participant(debate, participant_id),
        viewer_mode=viewer_mode,
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client.host if request.client else ""
    return client or "unknown"


def _speaker_id_for_side_position(side: str, position: int) -> str:
    prefix = "aff" if side == "affirmative" else "neg"
    return f"{prefix}_{position}"


def _active_seat(debate: DebateState) -> tuple[str, int] | None:
    match = re.match(r"^(aff|neg)_(\d)$", debate.active_speaker_id or "")
    if not match:
        return None
    return ("affirmative" if match.group(1) == "aff" else "negative", int(match.group(2)))


def _rename_agent_for_participant(debate: DebateState, participant: OnlineParticipant) -> None:
    speaker_id = participant_speaker_id(participant)
    if not speaker_id:
        return
    for agent in debate.agents:
        if agent.id == speaker_id:
            agent.name = participant.name
            return


def _is_team_discussion_message(message: DebateMessage) -> bool:
    from app.services.message_visibility import is_internal_message

    return is_internal_message(message)


def _export_markdown(debate: DebateState, *, viewer_mode: str | None = None) -> str:
    mode = normalize_viewer_mode(viewer_mode)
    mode_label = {
        "context": "仅己方内容可见",
        "realistic": "仅己方内容可见",
        "god": "全部可见",
        "all_visible": "全部可见",
        "own_side_only": "仅己方内容可见",
    }.get(mode, mode)
    aff_score = debate.score.get("affirmative", 0)
    neg_score = debate.score.get("negative", 0)
    visible_agents = [agent for agent in debate.agents if agent.side in {"affirmative", "negative", "judge"}]
    lines = [
        "# 辩论训练复盘报告",
        "",
        f"> 辩题：**{debate.topic}**",
        "",
        "## 比赛设置",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 模式 | {debate.mode.value} |",
        f"| 内容范围 | {mode_label} |",
        f"| 赛制 | {debate.schedule_template} |",
        f"| 计时 | {debate.timing.value} · 每环节 {debate.turn_seconds}s |",
        f"| TTS | {'开启' if debate.tts_enabled else '关闭'} |",
        f"| 当前环节 | {debate.phase} / {debate.segment_label} |",
        f"| 最终/当前比分 | 正方 {aff_score:.2f} · 反方 {neg_score:.2f} |",
        f"| 导出时间 | {utc_now().isoformat(timespec='seconds')} |",
        "",
        "## 双方阵容",
        "",
        "| 席位 | 姓名 | 模型 | 人设摘要 |",
        "| --- | --- | --- | --- |",
    ]
    for agent in visible_agents:
        if agent.side == "judge":
            seat = "裁判"
        else:
            seat = f"{'正方' if agent.side == 'affirmative' else '反方'}{agent.position}辩"
        lines.append(f"| {seat} | {agent.name} | {agent.model} | {agent.persona} |")
    lines.extend(
        [
            "",
            "## 赛程摘要",
            "",
            "| 进度 | 环节 | 阶段 | 状态 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in debate.schedule:
        lines.append(f"| {item.index + 1} | {item.label} | {item.phase} | {item.status} |")
    lines.append("")

    if debate.match_summary:
        lines.extend(["## 全场总结", "", debate.match_summary.strip(), ""])

    lines.extend(["## 时间线概览", ""])
    for index, m in enumerate(debate.messages, start=1):
        ts = m.created_at.isoformat(timespec="seconds") if m.created_at else ""
        scope = "队内" if _is_team_discussion_message(m) else "公开"
        lines.append(f"{index}. [{scope}] **{m.speaker_name}** · {m.segment_label or m.phase} · `{m.side}` · {ts}")
    lines.append("")

    def _append_message_block(m: DebateMessage) -> None:
        lines.append(f"#### {m.speaker_name} · {m.segment_label or m.phase}")
        meta = f"`{m.side}`"
        if m.created_at:
            meta += f" · {m.created_at.isoformat(timespec='seconds')}"
        if m.score_delta is not None:
            meta += f" · 得分 {m.score_delta:+.2f}"
        lines.append(f"*{meta}*")
        lines.append("")
        lines.append((m.content or "").strip())
        if m.score_reason:
            lines.append("")
            lines.append(f"> 评分理由：{m.score_reason}")
        if m.sources:
            lines.append("")
            lines.append("**引用资料**")
            for s in m.sources:
                sid = getattr(s, "id", None) or s.model_dump().get("id", "")
                lines.append(f"- `[{sid}]` **{s.title}** — {s.excerpt}")
        if mode in {"context", "god"} and (m.private_thought or m.strategy):
            lines.append("")
            lines.append("**AI 内部备注**")
            if m.strategy:
                lines.append(f"- 策略：{m.strategy}")
            if m.private_thought:
                lines.append(f"- 反思：{m.private_thought}")
        lines.append("")

    for section_title, predicate in (
        ("公开发言", lambda m: not _is_team_discussion_message(m) and not (m.side == "judge" and m.phase == "post_match" and "输出裁判报告" not in (m.segment_label or ""))),
        ("队内讨论", _is_team_discussion_message),
        ("裁判分析", lambda m: m.side == "judge" and m.phase == "post_match" and "输出裁判报告" not in (m.segment_label or "")),
    ):
        section_messages = [m for m in debate.messages if predicate(m)]
        if not section_messages:
            continue
        lines.extend([f"## {section_title}", ""])
        current_label = ""
        for m in section_messages:
            label = m.segment_label or m.phase
            if label != current_label:
                current_label = label
                lines.extend([f"### {label}", ""])
            _append_message_block(m)

    verdict = [
        m
        for m in debate.messages
        if m.side == "judge" and "输出裁判报告" in (m.segment_label or "")
    ]
    if verdict:
        lines.extend(["## 裁判终局报告", ""])
        for m in verdict:
            lines.append((m.content or "").strip())
            lines.append("")

    if not debate.messages:
        lines.extend(["## 发言记录", "", "本场暂未产生发言。", ""])

    return "\n".join(lines).rstrip() + "\n"


def _side_from_text(text: str) -> str:
    lowered = text.lower()
    if "affirmative" in lowered or "正方" in text:
        return "affirmative"
    if "negative" in lowered or "反方" in text:
        return "negative"
    if "judge" in lowered or "裁判" in text or "主席" in text:
        return "judge"
    return "assistant"


def _phase_from_label(label: str) -> str:
    if "自由辩论" in label:
        return "free_debate"
    if "质辩" in label or "盘问" in label or "质询" in label:
        return "cross_examination"
    if "总结" in label:
        return "closing"
    if "驳立论" in label or "驳论" in label or "对辩" in label:
        return "rebuttal"
    if "立论" in label:
        return "opening_statement"
    if "赛前" in label or "开场" in label:
        return "pre_match"
    if "裁判" in label or "判定" in label or "终局" in label:
        return "post_match"
    return "opening_statement"


def _normalize_user_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="发言内容不能为空")
    return text



def _speaker_id_for_user_message(debate: DebateState, participant: OnlineParticipant | None, payload: UserMessageCreate) -> str:
    return speaker_id_for_user_message(debate, participant, payload)


def _is_internal_user_turn(debate: DebateState, payload: UserMessageCreate) -> bool:
    from app.services.message_visibility import is_internal_message

    probe = DebateMessage(
        debate_id=debate.id,
        speaker_id=_speaker_id_for_user_message(debate, None, payload),
        speaker_name=payload.speaker_name,
        side=payload.side,
        content=payload.content,
        phase=debate.phase,
        segment_label=debate.segment_label,
    )
    return is_internal_message(probe)


def _teammate_reminder_agent(debate: DebateState, side: str, current_position: int):
    preferred = [2, 3, 4, 1]
    for position in preferred:
        if position == current_position:
            continue
        agent = next((a for a in debate.agents if a.side == side and a.position == position), None)
        if agent:
            return agent
    return next((a for a in debate.agents if a.side == side), None)


async def _accept_user_message(
    debate: DebateState,
    payload: UserMessageCreate,
    participant: OnlineParticipant | None,
    *,
    review: UserSpeechReview,
    public_debate: bool,
) -> DebateState:
    """统一入库用户发言：恰当则加分，不当则静默扣分并推进（赛中不插播裁判警告）。"""
    internal = _is_internal_user_turn(debate, payload)
    debate = await accept_user_message(
        debate,
        payload,
        participant,
        review=review,
        public_debate=public_debate,
        internal=internal,
        camera_status=confidence_manager.status(),
    )

    debate = await _persist_and_broadcast(debate, "message_added")
    changelog_title = (
        f"用户发言 · {debate.segment_label}"
        if review.acceptable
        else f"用户发言不当已记录 · {debate.segment_label}"
    )
    append_changelog(
        changelog_title,
        f"房间 `{debate.id}` · {payload.speaker_name}（{payload.side}）\n\n{payload.content[:500]}",
    )
    if not debate.awaiting_user:
        resume_auto(debate.id)
    return debate


async def _record_low_information_user_message(
    debate: DebateState,
    payload: UserMessageCreate,
    *,
    reason: str,
) -> DebateState:
    """兼容旧调用：转交统一入库路径。"""
    return await _accept_user_message(
        debate,
        payload,
        None,
        review=UserSpeechReview(acceptable=False, reason=reason, penalty=0.5),
        public_debate=not _is_internal_user_turn(debate, payload),
    )


def _parse_imported_markdown(payload: DebateImport) -> DebateState:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="导入内容不能为空")

    title_match = re.search(r"^#\s+(.+?)\s*$", content, flags=re.MULTILINE)
    topic = title_match.group(1).strip() if title_match else payload.filename.replace(".md", "").strip()
    agents = default_agents()
    debate = DebateState(
        topic=topic or "导入的历史辩论",
        mode=DebateMode.ai_autonomous,
        visibility="context",
        timing="unlimited",
        turn_seconds=90,
        format="formal",
        agents=agents,
        workflow=workflow_template(),
        phase="finished",
        segment_label="导入的历史记录",
        segment_seconds=0,
        auto_running=False,
        awaiting_user=False,
        match_summary="",
    )

    summary_match = re.search(r"##\s+全场总结\s+([\s\S]*?)(?=\n##\s+|\Z)", content)
    if summary_match:
        debate.match_summary = summary_match.group(1).strip()

    score_match = re.search(r"比分:\s*正方\s*([0-9.]+)\s*·\s*反方\s*([0-9.]+)", content)
    if score_match:
        debate.score = {"affirmative": float(score_match.group(1)), "negative": float(score_match.group(2))}

    agent_by_name = {agent.name: agent for agent in agents}
    heading_matches = list(re.finditer(r"^###\s+(.+?)\s*$", content, flags=re.MULTILINE))
    for index, match in enumerate(heading_matches):
        heading = match.group(1).strip()
        start = match.end()
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(content)
        body = content[start:end].strip()
        if not body or heading.startswith("本轮检索资料"):
            continue

        speaker_name = heading
        side = "assistant"
        label = "导入记录"
        export_match = re.match(r"(.+?)（(.+?)）·\s*(.+)", heading)
        client_match = re.match(r"(.+?)\s+·\s*(.+)", heading)
        if export_match:
            speaker_name = export_match.group(1).strip()
            side = _side_from_text(export_match.group(2))
            label = export_match.group(3).strip()
        elif client_match:
            speaker_name = client_match.group(1).strip()
            label = client_match.group(2).strip()
            side = _side_from_text(f"{speaker_name} {label}")

        agent = agent_by_name.get(speaker_name)
        if agent:
            side = agent.side
            speaker_id = agent.id
        else:
            speaker_id = side if side in {"judge", "assistant"} else f"imported_{index + 1}"

        debate.messages.append(
            DebateMessage(
                debate_id=debate.id,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                side=side,
                phase=_phase_from_label(label),
                segment_label=label,
                content=body,
                sources=[],
            )
        )

    if not debate.messages:
        raise HTTPException(status_code=400, detail="未识别到可导入的发言记录，请使用本项目导出的 Markdown")

    debate.turn_index = len(debate.messages)
    debate.schedule = build_schedule_status(10_000, debate.schedule_template)
    return debate


async def _persist_and_broadcast(debate: DebateState, event: str) -> DebateState:
    payload = debate.model_dump(mode="json")
    await save_debate(payload)
    await cache_set(f"debate:{debate.id}", payload)
    await cache_publish(f"debate:{debate.id}", {"event": event, "debate": payload})
    await manager.broadcast_state(debate.id, event, debate, _payload_for_viewer_request)
    return debate


@router.get("")
async def debates() -> list[dict]:
    return await list_debates()


@router.get("/schedules")
async def schedule_templates() -> dict:
    return {"templates": list_schedule_templates_meta()}


@router.get("/runtime-settings")
async def runtime_settings() -> dict:
    saved = load_runtime_settings()
    api_keys = merged_api_keys(saved)
    return {
        "api_keys": api_keys,
        "api_key_masks": {provider: mask_key(value) for provider, value in api_keys.items()},
        "models": saved.models,
        "defaults": saved.defaults,
    }


@router.put("/runtime-settings")
async def update_runtime_settings(payload: RuntimeSettings) -> dict:
    saved = apply_runtime_settings(payload)
    api_keys = merged_api_keys(saved)
    return {
        "status": "saved",
        "api_keys": api_keys,
        "api_key_masks": {provider: mask_key(value) for provider, value in api_keys.items()},
        "models": saved.models,
        "defaults": saved.defaults,
    }


@router.post("/demo")
async def removed_demo_debate() -> None:
    raise HTTPException(status_code=404, detail="快速演示模式已移除")


def _merge_opening_evidence_from_prep(debate: DebateState, prep: DebateState | None) -> None:
    if prep is None or prep.topic != debate.topic:
        return
    for side in ("affirmative", "negative"):
        add_argument_items(debate, side, prep.argument_bank.get(side, []))
    debate.argument_bank_locked = debate.argument_bank_locked or prep.argument_bank_locked


@router.post("/opening-evidence-prep", dependencies=[Depends(enforce_create_room_limit)])
async def prepare_opening_evidence(payload: DebateCreate) -> dict:
    prep = DebateState(
        topic=payload.topic,
        mode=payload.mode,
        visibility=_visibility_for_created_room(payload),
        timing=payload.timing,
        turn_seconds=payload.turn_seconds,
        format=payload.format,
        schedule_template=payload.schedule_template or "formal_4v4",
        agents=default_agents(),
        workflow=workflow_template(),
        auto_running=False,
    )
    init_schedule(prep)
    prep.schedule = build_schedule_status(prep.schedule_index, prep.schedule_template)
    for material in payload.materials:
        if not material.content.strip():
            continue
        material_sources = ingest_materials(
            debate_id=prep.id,
            title=material.title or "辩题参考资料",
            content=material.content,
        )
        await add_sources_to_argument_bank_with_ai_titles(prep, material_sources)
    await _persist_and_broadcast(prep, "opening_evidence_prep_created")
    warm_opening_evidence(prep)
    return {
        "prep_id": prep.id,
        "topic": prep.topic,
        "opening_argument_bank_ready": opening_argument_bank_ready(prep),
        "argument_bank": {
            side: [item.model_dump(mode="json") for item in prep.argument_bank.get(side, [])]
            for side in ("affirmative", "negative")
        },
    }


@router.delete("/opening-evidence-prep/{prep_id}")
async def cancel_opening_evidence_prep(prep_id: str) -> dict:
    cancel_opening_evidence_warmup(prep_id)
    return {"status": "cancelled", "prep_id": prep_id}


@router.post("/opening-training/analyze")
async def analyze_opening_training(payload: OpeningTrainingAnalyze) -> dict:
    try:
        return analyze_opening_draft(payload.topic, payload.side, payload.draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/opening-training/auto-improve")
async def auto_improve_opening_training(payload: OpeningTrainingAutoImprove) -> dict:
    try:
        return await auto_improve_opening_draft(payload.topic, payload.side, payload.max_rounds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/opening-training/auto-improve/stream")
async def auto_improve_opening_training_stream(payload: OpeningTrainingAutoImprove):
    async def event_stream():
        async for event in auto_improve_opening_draft_events(payload.topic, payload.side, payload.max_rounds):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/opening-training/polish")
async def polish_opening_training(payload: OpeningTrainingPolish) -> dict:
    try:
        return await polish_opening_draft(payload.topic, payload.side, payload.draft, payload.advice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", dependencies=[Depends(enforce_create_room_limit)])
async def create_debate(payload: DebateCreate) -> dict:
    ensure_project_index()
    agents = default_agents()
    for agent in agents:
        if agent.id in payload.models:
            agent.model = payload.models[agent.id]

    user_side = payload.user_side or user_side_for_mode(payload.mode)
    user_position = payload.user_position if payload.user_position in {1, 2, 3, 4} else 1
    user_name = (payload.user_name or "用户辩手").strip()[:24] or "用户辩手"
    if user_side:
        for agent in agents:
            if agent.side == user_side and agent.position == user_position:
                agent.name = user_name

    template = payload.schedule_template or "formal_4v4"
    debate = DebateState(
        topic=payload.topic,
        mode=payload.mode,
        visibility=_visibility_for_created_room(payload),
        timing=payload.timing,
        turn_seconds=payload.turn_seconds,
        format=payload.format,
        schedule_template=template,
        user_side=user_side,
        user_position=user_position,
        user_name=user_name,
        tts_enabled=payload.tts_enabled,
        human_timeout_penalty_enabled=(
            False if payload.mode == DebateMode.ai_autonomous else payload.human_timeout_penalty_enabled
        ),
        agents=agents,
        workflow=workflow_template(),
    )
    _lock_initial_rules(debate)
    init_schedule(debate)
    debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)
    for material in payload.materials:
        if not material.content.strip():
            continue
        material_sources = ingest_materials(
            debate_id=debate.id,
            title=material.title or "辩题参考资料",
            content=material.content,
        )
        await add_sources_to_argument_bank_with_ai_titles(debate, material_sources)
    if payload.opening_evidence_prep_id:
        prep_doc = await get_debate(payload.opening_evidence_prep_id)
        prep = DebateState.model_validate(prep_doc) if prep_doc is not None else None
        _merge_opening_evidence_from_prep(debate, prep)

    if payload.mode == DebateMode.online_match:
        debate.online_ready = False
        debate.materials_preview = [m for m in payload.materials if m.content.strip()]
        if payload.session_id:
            debate.online_session_id = payload.session_id.strip()
            link_session(debate.online_session_id, debate.id, debate.topic)

    mode_label = {
        DebateMode.ai_autonomous: "AI 自主辩论",
        DebateMode.user_affirmative: "用户加入正方",
        DebateMode.user_negative: "用户加入反方",
        DebateMode.online_match: "多人联机辩论",
    }[payload.mode]
    if payload.mode in {DebateMode.user_affirmative, DebateMode.user_negative} and user_side:
        mode_label = f"用户加入{'正方' if user_side == 'affirmative' else '反方'}{user_position}辩"
    append_changelog(
        f"创建辩论 · {mode_label}",
        f"辩题：{debate.topic}\n房间 ID：`{debate.id}`\n模式：{mode_label}",
    )

    if payload.mode == DebateMode.online_match:
        debate.auto_running = False
        create_event = "debate_created"
        host_token = issue_host_token(debate.id)
    elif payload.mode == DebateMode.ai_autonomous or not needs_user_turn(debate):
        debate.auto_running = True
        create_event = "debate_created"
        host_token = None
    else:
        debate.awaiting_user = True
        mark_user_wait_start(debate)
        create_event = "awaiting_user"
        host_token = None

    debate = await _persist_and_broadcast(debate, create_event)
    warm_opening_evidence(debate)
    if debate.auto_running:
        start_auto(debate.id)
    asyncio.create_task(_index_debate_materials_background(payload.topic, debate.id, []))

    try:
        from app.services.usage_log import record_debate_created
        record_debate_created(debate.id, debate.topic, debate.mode.value)
    except Exception:
        pass

    payload_out = debate.model_dump(mode="json")
    if host_token:
        payload_out["host_token"] = host_token
    return payload_out


@router.post("/import", dependencies=[Depends(enforce_create_room_limit)])
async def import_debate_history(payload: DebateImport) -> DebateState:
    debate = _parse_imported_markdown(payload)
    debate = await _persist_and_broadcast(debate, "debate_imported")
    append_changelog(
        "导入历史记录",
        f"文件：`{payload.filename}`\n房间 ID：`{debate.id}`\n发言数：{len(debate.messages)}",
    )
    return debate


@router.get("/online-lobby")
async def online_lobby() -> dict:
    docs = await list_debates()
    rooms = []
    for doc in docs:
        if doc.get("mode") != DebateMode.online_match.value:
            continue
        if doc.get("phase") == "finished":
            continue
        participants = doc.get("participants") or []
        online_count = sum(1 for p in participants if p.get("connected"))
        rooms.append(
            {
                "id": doc.get("id"),
                "topic": doc.get("topic", ""),
                "phase": doc.get("phase", ""),
                "segment_label": doc.get("segment_label", ""),
                "online_count": online_count,
                "join_path": f"/join/{doc.get('id')}",
            }
        )
    rooms.sort(key=lambda r: (r.get("online_count", 0), r.get("id", "")), reverse=True)
    return {"rooms": rooms[:30], "count": len(rooms)}


@router.post("/online-session")
async def create_online_session() -> dict:
    session_id = create_online_session_id()
    return {"session_id": session_id, "join_path": f"/join/session/{session_id}"}


@router.get("/online-session/{session_id}")
async def online_session_status(session_id: str) -> dict:
    entry = get_session(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="邀请会话不存在或已过期")
    debate_id = entry.get("debate_id")
    if not debate_id:
        return {
            "status": "waiting",
            "session_id": session_id,
            "debate_id": None,
            "online_ready": False,
            "message": "对方正在创建房间中，请稍候…",
        }
    doc = await get_debate(str(debate_id))
    if doc is None:
        return {
            "status": "waiting",
            "session_id": session_id,
            "debate_id": None,
            "online_ready": False,
            "message": "对方正在创建房间中，请稍候…",
        }
    online_ready = bool(doc.get("online_ready"))
    if online_ready:
        return {
            "status": "ready",
            "session_id": session_id,
            "debate_id": doc.get("id"),
            "topic": doc.get("topic", ""),
            "online_ready": True,
            "message": "可以加入了",
        }
    return {
        "status": "preparing",
        "session_id": session_id,
        "debate_id": doc.get("id"),
        "topic": doc.get("topic", ""),
        "online_ready": False,
        "message": "等待房主开启房间…",
    }


@router.get("/{debate_id}")
async def get_debate_state(
    debate_id: str,
    viewer_side: str | None = None,
    participant_id: str | None = None,
    viewer_mode: str | None = None,
) -> dict:
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    return _payload_for_viewer_request(
        debate,
        viewer_side=viewer_side,
        participant_id=participant_id,
        viewer_mode=viewer_mode,
    )


@router.post("/{debate_id}/participants")
async def join_debate_participant(debate_id: str, payload: ParticipantJoin, request: Request) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.phase == "finished":
        raise HTTPException(status_code=400, detail="辩论已结束，不能加入联机席位")

    side = payload.side
    if debate.mode == DebateMode.online_match:
        if side == "spectator":
            raise HTTPException(status_code=400, detail="联机模式仅支持辩手席位，请选择正方或反方")
        if side not in {"affirmative", "negative"}:
            raise HTTPException(status_code=400, detail="联机模式仅支持辩手席位")
    position = 0 if side == "spectator" else payload.position
    if side in {"affirmative", "negative"} and position not in {1, 2, 3, 4}:
        raise HTTPException(status_code=400, detail="辩手席位必须选择一至四辩")

    participant_id = payload.participant_id or str(uuid4())
    name = (payload.name or "联机辩手").strip()[:24] or "联机辩手"
    existing = _find_participant(debate, participant_id)

    if debate.mode == DebateMode.online_match and not debate.online_ready and not existing:
        occupied = [
            p
            for p in debate.participants
            if p.connected and p.side in {"affirmative", "negative"}
        ]
        if occupied:
            raise HTTPException(status_code=403, detail="房主尚未完成准备，请稍候…")

    if side != "spectator":
        occupied = next(
            (
                p
                for p in debate.participants
                if p.id != participant_id and p.connected and p.side == side and p.position == position
            ),
            None,
        )
        if occupied:
            raise HTTPException(status_code=409, detail=f"该席位已被 {occupied.name} 占用")

    if existing:
        existing.name = name
        existing.side = side
        existing.position = position
        existing.connected = True
        existing.last_ip = _client_ip(request)
        existing.updated_at = utc_now()
        participant = existing
    else:
        participant = OnlineParticipant(
            id=participant_id,
            name=name,
            side=side,
            position=position,
            last_ip=_client_ip(request),
        )
        debate.participants.append(participant)

    if side != "spectator":
        _rename_agent_for_participant(debate, participant)
        if (
            debate.mode == DebateMode.online_match
            and participant_speaker_id(participant) == debate.active_speaker_id
            and debate.phase not in {"opening_prep", "free_prep", "closing_prep"}
        ):
            debate.awaiting_user = True
            debate.auto_running = False
            stop_auto(debate.id)

    if (
        debate.mode == DebateMode.online_match
        and debate.online_ready
        and side in {"affirmative", "negative"}
        and not debate.awaiting_user
        and debate.phase != "finished"
        and not debate.auto_running
    ):
        debate.auto_running = True

    debate.updated_at = utc_now()
    debate = await _persist_and_broadcast(debate, "participant_joined")
    participant_payload = participant.model_dump(mode="json")
    response_debate = _payload_for_viewer_request(debate, participant_id=participant.id)

    if debate.mode == DebateMode.online_match and debate.online_ready and debate.auto_running:
        resume_auto(debate.id)
    return {
        "participant": participant_payload,
        "debate": response_debate,
    }


@router.post("/{debate_id}/online-ready")
async def mark_online_ready(
    debate_id: str,
    request: Request,
    host_token: str = Form(default=""),
) -> dict:
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode != DebateMode.online_match:
        raise HTTPException(status_code=400, detail="仅联机模式可标记就绪")
    token = host_token or request.headers.get("x-host-token", "")
    if not verify_host_token(debate_id, token):
        raise HTTPException(status_code=403, detail="需要房主权限才能开启房间")
    debate.online_ready = True
    debate.updated_at = utc_now()
    if (
        not debate.awaiting_user
        and debate.phase != "finished"
        and not debate.auto_running
    ):
        debate.auto_running = True
    debate = await _persist_and_broadcast(debate, "online_ready")
    response_debate = _payload_for_viewer_request(debate)
    if debate.auto_running:
        resume_auto(debate.id)
    return {
        "online_ready": True,
        "debate": response_debate,
    }


@router.post("/{debate_id}/participants/{participant_id}/kick")
async def kick_participant(
    debate_id: str,
    participant_id: str,
    request: Request,
    host_token: str = Form(default=""),
) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode != DebateMode.online_match:
        raise HTTPException(status_code=400, detail="仅多人联机模式支持踢人")
    token = host_token or request.headers.get("x-host-token", "")
    if not verify_host_token(debate_id, token):
        raise HTTPException(status_code=403, detail="主持台权限校验失败，请使用房主设备操作")

    participant = _find_participant(debate, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    participant.connected = False
    participant.updated_at = utc_now()
    debate.updated_at = utc_now()
    presence.cancel_pending_offline(debate_id, participant_id)
    await manager.disconnect_participant(debate_id, participant_id)
    debate = await _persist_and_broadcast(debate, "participant_kicked")
    participant_name = participant.name
    response_debate = _payload_for_viewer_request(debate)
    append_ops_event(
        "host_control",
        "主持人移出联机成员",
        debate_id=debate_id,
        participant_id=participant_id,
        participant_name=participant_name,
    )
    return {"status": "kicked", "participant_id": participant_id, "debate": response_debate}


@router.get("/{debate_id}/export.md", response_class=PlainTextResponse)
async def export_debate_markdown(
    debate_id: str,
    viewer_side: str | None = None,
    participant_id: str | None = None,
    viewer_mode: str | None = None,
) -> PlainTextResponse:
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    filtered = _payload_for_viewer_request(
        debate,
        viewer_side=viewer_side,
        participant_id=participant_id,
        viewer_mode=viewer_mode,
    )
    export_debate = debate.model_copy(deep=True)
    export_debate.messages = [DebateMessage.model_validate(m) for m in filtered["messages"]]
    body = _export_markdown(export_debate, viewer_mode=filtered.get("viewer_mode"))
    return PlainTextResponse(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="debate-{debate_id}.md"'},
    )


@router.get("/{debate_id}/export.pdf")
async def export_debate_pdf(
    debate_id: str,
    viewer_side: str | None = None,
    participant_id: str | None = None,
    viewer_mode: str | None = None,
) -> Response:
    """由 export.md 同源内容生成 PDF。"""
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    filtered = _payload_for_viewer_request(
        debate,
        viewer_side=viewer_side,
        participant_id=participant_id,
        viewer_mode=viewer_mode,
    )
    export_debate = debate.model_copy(deep=True)
    export_debate.messages = [DebateMessage.model_validate(m) for m in filtered["messages"]]
    md_body = _export_markdown(export_debate, viewer_mode=filtered.get("viewer_mode"))
    try:
        pdf_bytes = markdown_to_pdf_bytes(md_body)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {exc}") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="debate-{debate_id}.pdf"'},
    )


@router.get("/{debate_id}/llm-stats")
async def debate_llm_stats(debate_id: str) -> dict:
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    return await get_debate_llm_stats(debate_id)


@router.post("/{debate_id}/materials")
async def upload_debate_materials(
    debate_id: str,
    payload: MaterialUpload,
    request: Request,
) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="资料内容不能为空")
    sources = ingest_materials(
        debate_id=debate_id,
        title=payload.title,
        content=payload.content,
        replace=payload.replace,
    )
    debate = _state_from_doc(doc)
    added = await add_sources_to_argument_bank_with_ai_titles(debate, sources)
    debate.updated_at = utc_now()
    await save_debate(debate.model_dump(mode="json"))
    await cache_set(f"debate:{debate.id}", debate.model_dump(mode="json"))
    return {
        "status": "ok",
        "chunks": len(sources),
        "sources": [s.model_dump() for s in sources],
        "argument_bank_added": added,
    }


@router.post("/{debate_id}/materials/file")
async def upload_debate_materials_file(
    debate_id: str,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form("上传文件"),
    replace: bool = Form(False),
) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="仅支持 UTF-8 文本文件（.txt / .md）") from None
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")
    sources = ingest_materials(
        debate_id=debate_id,
        title=title or file.filename or "上传文件",
        content=content,
        replace=replace,
    )
    debate = _state_from_doc(doc)
    added = await add_sources_to_argument_bank_with_ai_titles(debate, sources)
    debate.updated_at = utc_now()
    await save_debate(debate.model_dump(mode="json"))
    await cache_set(f"debate:{debate.id}", debate.model_dump(mode="json"))
    return {
        "status": "ok",
        "filename": file.filename,
        "chunks": len(sources),
        "sources": [s.model_dump() for s in sources],
        "argument_bank_added": added,
    }


@router.put("/{debate_id}/user-draft")
async def save_user_draft(debate_id: str, payload: UserDraftUpdate, request: Request) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式无需保存用户草稿")
    debate.user_draft = payload.draft or ""
    debate.updated_at = utc_now()
    await save_debate(debate.model_dump(mode="json"))
    await cache_set(f"debate:{debate.id}", debate.model_dump(mode="json"))
    return {"status": "saved", "chars": len(debate.user_draft)}


@router.post("/{debate_id}/message")
async def post_user_message(debate_id: str, payload: UserMessageCreate, request: Request) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)

    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="当前为 AI 自主模式，不支持用户发言")

    participant: OnlineParticipant | None = None
    if debate.mode == DebateMode.online_match:
        participant = _find_participant(debate, payload.participant_id)
        if participant is None or participant.side == "spectator":
            raise HTTPException(status_code=403, detail="请先通过邀请链接加入一个辩手席位")
        active_seat = _active_seat(debate)
        if active_seat is None:
            raise HTTPException(status_code=400, detail="当前环节不是双方辩手发言")
        expected_side, expected_position = active_seat
        if participant.side != expected_side or participant.position != expected_position:
            raise HTTPException(status_code=409, detail="现在不是你的发言回合")
        payload.side = participant.side
        payload.position = participant.position
        payload.speaker_name = participant.name
    else:
        expected = debate_user_side(debate)
        if expected and payload.side != expected:
            raise HTTPException(status_code=400, detail=f"当前模式仅允许 {expected} 方发言")
        if expected:
            payload.side = expected
            payload.position = debate_user_position(debate)
            payload.speaker_name = (debate.user_name or "用户辩手").strip() or "用户辩手"

    internal_prep = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
    if internal_prep and not is_user_task_assign_segment(debate) and not is_user_team_discussion_segment(debate):
        raise HTTPException(status_code=400, detail="当前为队内准备环节，无需用户发言")
    if not opening_team_discussion_ready(debate):
        debate.awaiting_user = False
        debate.auto_running = True
        clear_user_wait(debate)
        debate.updated_at = utc_now()
        await _persist_and_broadcast(debate, "opening_argument_bank_required")
        resume_auto(debate.id)
        raise HTTPException(status_code=409, detail="论据库尚未搜集完成，请等待正反方论据各达到 10 条后再进入队内讨论")
    if not needs_user_turn(debate) and not debate.awaiting_user:
        raise HTTPException(status_code=400, detail="当前环节不需要用户发言")

    payload.content = _normalize_user_content(payload.content)
    public_debate = not _is_internal_user_turn(debate, payload)
    if public_debate:
        ok, reason = enforce_argument_citations(debate, payload.side, payload.content)
        if not ok:
            raise HTTPException(status_code=400, detail=reason)
    speech_review = await review_user_speech(debate, payload, public_debate=public_debate)
    debate = await _accept_user_message(
        debate,
        payload,
        participant,
        review=speech_review,
        public_debate=public_debate,
    )
    return _payload_for_viewer_request(
        debate,
        viewer_side=payload.side,
        participant_id=payload.participant_id,
        viewer_mode=request.query_params.get("viewer_mode"),
    )


@router.post("/{debate_id}/speech-to-text")
async def speech_to_text(debate_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式无需用户语音录入")
    audio = await file.read()
    try:
        result = await recognize_speech(audio, audio_format="wav")
    except ASRError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "text": result["text"],
        "status": result["status"],
        "bytes": len(audio),
    }


@router.post("/{debate_id}/resume")
async def resume_debate(debate_id: str, request: Request) -> dict[str, str]:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    resume_auto(debate_id)
    return {"status": "resumed"}


@router.post("/{debate_id}/tts/stop")
async def stop_debate_tts(debate_id: str, request: Request) -> dict[str, str | bool]:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    debate.tts_enabled = False
    debate.updated_at = utc_now()
    await _persist_and_broadcast(debate, "tts_stopped")
    return {"status": "stopped", "tts_enabled": False}


@router.post("/{debate_id}/host-control")
async def host_control_debate(
    debate_id: str,
    request: Request,
    action: str = Form(...),
    host_token: str = Form(default=""),
) -> dict[str, str]:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode != DebateMode.online_match:
        raise HTTPException(status_code=400, detail="仅多人联机模式支持主持控制")
    token = host_token or request.headers.get("x-host-token", "")
    if not verify_host_token(debate_id, token):
        raise HTTPException(status_code=403, detail="主持台权限校验失败，请使用房主设备操作")
    if action == "pause":
        stop_auto(debate_id)
        debate.auto_running = False
        debate.updated_at = utc_now()
        await _persist_and_broadcast(debate, "host_control")
        append_ops_event("host_control", "主持人暂停自动推进", debate_id=debate_id)
        return {"status": "paused"}
    if action == "resume":
        resume_auto(debate_id)
        append_ops_event("host_control", "主持人恢复自动推进", debate_id=debate_id)
        return {"status": "resumed"}
    if action == "next":
        async def on_event(evt: dict) -> None:
            await _broadcast_debate_event(debate_id, debate, evt)

        next_state = await debate_graph.run_turn_streaming(debate, on_event=on_event)
        await _persist_and_broadcast(next_state, "debate_stepped")
        append_ops_event("host_control", "主持人推进下一环节", debate_id=debate_id)
        return {"status": "stepped"}
    raise HTTPException(status_code=400, detail="action 仅支持 pause/resume/next")


@router.post("/{debate_id}/assist")
async def assist_user(debate_id: str, payload: AssistRequest, request: Request) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式不提供用户辅助")
    return await generate_assist(debate, payload.side, payload.draft, payload.position)


@router.post("/{debate_id}/assist/stream")
async def assist_user_stream(debate_id: str, payload: AssistRequest, request: Request):
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式不提供用户辅助")

    async def event_stream():
        async for event in generate_assist_stream_events(debate, payload.side, payload.draft, payload.position):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: {\"type\":\"end\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{debate_id}/assist/draft")
async def assist_draft(debate_id: str, payload: AssistRequest, request: Request) -> dict:
    """人机模式：代拟可提交的发言草稿。"""
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式不提供用户辅助")
    return await generate_draft(debate, payload.side, payload.draft, payload.position)


@router.post("/{debate_id}/assist/draft/stream")
async def assist_draft_stream(debate_id: str, payload: AssistRequest, request: Request):
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)
    if debate.mode == DebateMode.ai_autonomous:
        raise HTTPException(status_code=400, detail="AI 自主模式不提供用户辅助")

    async def event_stream():
        async for event in generate_draft_stream_events(debate, payload.side, payload.draft, payload.position):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: {\"type\":\"end\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{debate_id}/share")
async def debate_share_meta(debate_id: str) -> dict:
    """只读回放分享元数据（路径供前端拼完整 URL）。"""
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    return {
        "debate_id": debate_id,
        "readonly": True,
        "path": f"/share/{debate_id}",
        "join_path": f"/join/{debate_id}",
        "topic": doc.get("topic", ""),
    }


@router.post("/{debate_id}/step")
async def step_debate(debate_id: str, request: Request) -> dict:
    enforce_write_limit(request)
    doc = await get_debate(debate_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Debate not found")
    debate = _state_from_doc(doc)

    async def on_event(evt: dict) -> None:
        await _broadcast_debate_event(debate_id, debate, evt)

    debate = await debate_graph.run_turn_streaming(debate, on_event=on_event)
    debate = await _persist_and_broadcast(debate, "debate_stepped")
    return _payload_for_viewer_request(
        debate,
        viewer_side=request.query_params.get("viewer_side"),
        participant_id=request.query_params.get("participant_id"),
        viewer_mode=request.query_params.get("viewer_mode"),
    )


@router.post("/{debate_id}/stop")
async def stop_debate_auto(debate_id: str) -> dict[str, str]:
    stop_auto(debate_id)
    return {"status": "stopped"}


async def _restore_participant_on_ws_connect(
    debate_id: str,
    participant_id: str | None,
) -> None:
    if not participant_id:
        return
    presence.cancel_pending_offline(debate_id, participant_id)
    doc = await get_debate(debate_id)
    if doc is None:
        return
    debate = _state_from_doc(doc)
    participant = _find_participant(debate, participant_id)
    if participant is None:
        return
    was_offline = not participant.connected
    participant.connected = True
    participant.updated_at = utc_now()
    debate.updated_at = utc_now()
    if was_offline:
        await _persist_and_broadcast(debate, "participant_presence_changed")
    else:
        await save_debate(debate.model_dump(mode="json"))


async def _mark_participant_offline(debate_id: str, participant_id: str) -> None:
    doc = await get_debate(debate_id)
    if doc is None:
        return
    debate = _state_from_doc(doc)
    participant = _find_participant(debate, participant_id)
    if participant is None or not participant.connected:
        return
    participant.connected = False
    participant.updated_at = utc_now()
    debate.updated_at = utc_now()
    await _persist_and_broadcast(debate, "participant_left")


@router.websocket("/ws/{debate_id}")
async def debate_socket(websocket: WebSocket, debate_id: str) -> None:
    viewer_side = websocket.query_params.get("viewer_side")
    participant_id = websocket.query_params.get("participant_id")
    viewer_mode = websocket.query_params.get("viewer_mode")
    await manager.connect(
        debate_id,
        websocket,
        viewer_side=viewer_side,
        participant_id=participant_id,
        viewer_mode=viewer_mode,
    )
    await _restore_participant_on_ws_connect(debate_id, participant_id)
    doc = await get_debate(debate_id)
    if doc:
        debate = _state_from_doc(doc)
        await websocket.send_json(
            {
                "event": "snapshot",
                "debate": _payload_for_viewer_request(
                    debate,
                    viewer_side=viewer_side,
                    participant_id=participant_id,
                    viewer_mode=viewer_mode,
                ),
            }
        )
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "ping":
                manager.touch(debate_id, websocket)
                await websocket.send_json({"type": "pong"})
                continue
            if data.get("type") == "update_viewer_mode":
                manager.update_connection_meta(
                    debate_id,
                    websocket,
                    viewer_side=data.get("viewer_side"),
                    viewer_mode=data.get("viewer_mode"),
                )
                continue
            if data.get("type") == "webrtc_signal":
                await manager.relay_signal(debate_id, websocket, data)
    except WebSocketDisconnect:
        entry = manager.disconnect(debate_id, websocket)
        disconnected_participant_id = entry.get("participant_id") if entry else None
        if not disconnected_participant_id:
            return

        def _still_connected() -> bool:
            return manager.participant_connection_count(debate_id, disconnected_participant_id) > 0

        presence.schedule_participant_offline(
            debate_id,
            disconnected_participant_id,
            is_still_connected=_still_connected,
            mark_offline=lambda: _mark_participant_offline(debate_id, disconnected_participant_id),
        )
