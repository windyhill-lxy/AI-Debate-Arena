import asyncio
import logging
from typing import Any

from app.db.mongo import get_debate, save_debate
from app.db.redis_cache import cache_publish, cache_set
from app.models import DebateMessage, DebateMode, DebateState
from app.services.changelog import append_changelog
from app.services.debate_mode import needs_user_turn, prepare_next_online_user_turn, user_side_for_mode
from app.services.speech_timeout import mark_user_wait_start
from app.services.debate_schedule_meta import advance_procedural_turn, is_procedural_segment
from app.services.online_room_lock import online_room_lock
from app.services.realtime import manager
from app.services.tts import TTSError, estimate_playback_seconds, markdown_to_speech_text, synthesize_message_audio, tts_profile_for_agent
from app.services.tts_policy import should_synthesize_tts
from app.workflow.debate_graph import debate_graph

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}
_runner_locks: dict[str, asyncio.Lock] = {}
_tts_message_tasks: dict[tuple[str, str], asyncio.Task] = {}
_tts_message_results: dict[tuple[str, str], DebateMessage] = {}


def _runner_lock(debate_id: str) -> asyncio.Lock:
    lock = _runner_locks.get(debate_id)
    if lock is None:
        lock = asyncio.Lock()
        _runner_locks[debate_id] = lock
    return lock


def _preserve_live_online_fields(debate: DebateState, latest: DebateState) -> None:
    debate.participants = latest.participants
    debate.online_ready = latest.online_ready
    debate.online_session_id = latest.online_session_id
    debate.materials_preview = latest.materials_preview


async def _broadcast(debate_id: str, event: str, payload: dict[str, Any]) -> None:
    message = {"event": event, **payload}
    await manager.broadcast(debate_id, message)
    await cache_publish(f"debate:{debate_id}", message)


from app.services.viewer_payload import debate_payload_for_viewer, resolve_viewer_side, streaming_event_visible


def _find_participant(debate: DebateState, participant_id: str | None):
    if not participant_id:
        return None
    return next((p for p in debate.participants if p.id == participant_id), None)


def _payload_for_connection(
    debate: DebateState,
    *,
    viewer_side: str | None = None,
    participant_id: str | None = None,
    viewer_mode: str | None = None,
) -> dict:
    return debate_payload_for_viewer(
        debate,
        viewer_side=viewer_side,
        participant=_find_participant(debate, participant_id),
        viewer_mode=viewer_mode,
    )


async def _broadcast_state(debate_id: str, event: str, debate: DebateState) -> None:
    await manager.broadcast_state(debate_id, event, debate, _payload_for_connection)
    await cache_publish(f"debate:{debate_id}", {"event": event})


async def _broadcast_debate_event(debate: DebateState, event: dict[str, Any]) -> None:
    await manager.broadcast_filtered(
        debate.id,
        event,
        lambda payload, connection: streaming_event_visible(
            debate,
            payload,
            viewer_side=resolve_viewer_side(
                debate,
                viewer_side=connection.get("viewer_side"),
                participant=_find_participant(debate, connection.get("participant_id")),
            ),
            viewer_mode=connection.get("viewer_mode"),
        ),
    )
    await cache_publish(f"debate:{debate.id}", {"event": event.get("type", "stream")})


async def _run_procedural_step(debate: DebateState) -> DebateState:
    """裁判流程环节：跳过 LLM 长发言，直接推进赛程。"""
    return advance_procedural_turn(debate)


async def recover_auto_runners() -> int:
    """服务启动后恢复未结束且应自动推进的房间。"""
    from app.db.mongo import list_debates_in_progress

    resumed = 0
    for doc in await list_debates_in_progress():
        debate = DebateState.model_validate(doc)
        if debate.phase == "finished" or debate.awaiting_user:
            continue
        if not debate.auto_running:
            continue
        task = _tasks.get(debate.id)
        if task is not None and not task.done():
            continue
        start_auto(debate.id)
        resumed += 1
        logger.info("recovered auto_runner for debate %s", debate.id)
    return resumed


async def _persist(debate: DebateState) -> None:
    data = debate.model_dump(mode="json")
    await save_debate(data)
    await cache_set(f"debate:{debate.id}", data)


async def _run_turn_with_events(debate: DebateState) -> DebateState:
    async def on_event(evt: dict[str, Any]) -> None:
        if evt.get("type") == "speech_end":
            _schedule_tts_audio_for_event(debate, evt)
        await _broadcast_debate_event(debate, evt)

    return await debate_graph.run_turn_streaming(debate, on_event=on_event)


async def _attach_tts_audio_to_message(debate: DebateState, message: DebateMessage) -> float:
    if not debate.tts_enabled:
        return 0.5
    if not should_synthesize_tts(debate, message):
        return 0.5
    if message.side not in {"affirmative", "negative", "judge"} or message.audio_url:
        return 2.0

    agent = next((item for item in debate.agents if item.id == message.speaker_id), None)
    tts_profile = tts_profile_for_agent(agent)
    await _broadcast_debate_event(
        debate,
        {
            "type": "speech_audio_start",
            "message_id": message.id,
            "speaker_id": message.speaker_id,
            "speaker_name": message.speaker_name,
            "side": message.side,
            "phase": message.phase,
            "segment_label": message.segment_label,
        },
    )
    async def on_chunk(done: int, total: int) -> None:
        await _broadcast_debate_event(
            debate,
            {
                "type": "speech_audio_progress",
                "message_id": message.id,
                "speaker_id": message.speaker_id,
                "speaker_name": message.speaker_name,
                "side": message.side,
                "phase": message.phase,
                "segment_label": message.segment_label,
                "chunk": done,
                "total": total,
            },
        )

    async def on_audio_delta(segment_index: int, audio_url: str) -> None:
        await _broadcast_debate_event(
            debate,
            {
                "type": "speech_audio_delta",
                "message_id": message.id,
                "speaker_id": message.speaker_id,
                "speaker_name": message.speaker_name,
                "side": message.side,
                "phase": message.phase,
                "segment_label": message.segment_label,
                "segment_index": segment_index,
                "audio_url": audio_url,
                "audio_urls": [audio_url],
                "voice": tts_profile.voice,
                "tts_backend": "dashscope_realtime",
            },
        )

    try:
        audio = await synthesize_message_audio(message, agent, on_chunk=on_chunk, on_audio_delta=on_audio_delta)
    except (TTSError, Exception) as exc:
        if not isinstance(exc, TTSError):
            logger.exception("TTS failed for message %s", message.id)
        await _broadcast_debate_event(
            debate,
            {
                "type": "speech_audio_error",
                "message_id": message.id,
                "speaker_id": message.speaker_id,
                "speaker_name": message.speaker_name,
                "side": message.side,
                "phase": message.phase,
                "segment_label": message.segment_label,
                "message": str(exc),
            },
        )
        text = markdown_to_speech_text(message.content)
        return estimate_playback_seconds(text, 1)

    message.audio_url = str(audio["audio_url"])
    message.audio_urls = [str(url) for url in audio.get("audio_urls", [])] or [message.audio_url]
    message.tts_voice = str(audio["voice"])
    message.tts_instructions = str(audio["instructions"])
    wait_sec = float(audio.get("playback_wait_sec") or 5.0)
    audio_urls = message.audio_urls
    await _broadcast_debate_event(
        debate,
        {
            "type": "speech_audio",
            "message_id": message.id,
            "speaker_id": message.speaker_id,
            "speaker_name": message.speaker_name,
            "side": message.side,
            "phase": message.phase,
            "segment_label": message.segment_label,
            "audio_url": message.audio_url,
            "audio_urls": audio_urls,
            "voice": message.tts_voice,
            "instructions": message.tts_instructions,
            "expires_at": audio["expires_at"],
            "playback_wait_sec": wait_sec,
            "tts_backend": audio.get("tts_backend") or "dashscope_http",
            "streamed_audio_delta_count": audio.get("streamed_audio_delta_count") or 0,
        },
    )
    return wait_sec


async def _attach_tts_audio(debate: DebateState) -> float:
    if not debate.messages:
        return 2.0
    target_message_id = debate.messages[-1].id
    doc = await get_debate(debate.id)
    if doc is not None:
        latest = DebateState.model_validate(doc)
        if latest.messages and latest.messages[-1].id == target_message_id:
            debate = latest
    return await _attach_tts_audio_to_message(debate, debate.messages[-1])


async def _persist_tts_message_audio(debate_id: str, source_message: DebateMessage) -> bool:
    if not source_message.audio_url:
        return False
    doc = await get_debate(debate_id)
    if doc is None:
        return False
    persisted = DebateState.model_validate(doc)
    for message in persisted.messages:
        if message.id == source_message.id:
            message.audio_url = source_message.audio_url
            message.audio_urls = source_message.audio_urls
            message.tts_voice = source_message.tts_voice
            message.tts_instructions = source_message.tts_instructions
            await _persist(persisted)
            await _broadcast_state(debate_id, "debate_audio_attached", persisted)
            return True
    return False


def _copy_tts_audio_fields(target: DebateMessage, source: DebateMessage) -> None:
    target.audio_url = source.audio_url
    target.audio_urls = source.audio_urls
    target.tts_voice = source.tts_voice
    target.tts_instructions = source.tts_instructions


def _schedule_tts_audio_for_message(debate: DebateState, message: DebateMessage) -> bool:
    if not debate.tts_enabled or not should_synthesize_tts(debate, message):
        return False
    if message.side not in {"affirmative", "negative", "judge"} or message.audio_url:
        return False
    key = (debate.id, message.id)
    existing = _tts_message_tasks.get(key)
    if existing is not None:
        result = _tts_message_results.get(key)
        if result is not None and result.audio_url:
            _copy_tts_audio_fields(message, result)
            asyncio.create_task(_persist_tts_message_audio(debate.id, result))
            return True
        if existing.done():
            _tts_message_tasks.pop(key, None)
        else:
            return True

    async def run() -> None:
        try:
            await _attach_tts_audio_to_message(debate, message)
            if message.audio_url:
                _tts_message_results[key] = message
                await _persist_tts_message_audio(debate.id, message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("background TTS attach failed for debate %s message %s", debate.id, message.id)

    _tts_message_tasks[key] = asyncio.create_task(run())
    return True


def _schedule_tts_audio_for_event(debate: DebateState, evt: dict[str, Any]) -> bool:
    content = str(evt.get("content") or "").strip()
    message_id = str(evt.get("message_id") or "").strip()
    if not content or not message_id:
        return False
    message = DebateMessage(
        id=message_id,
        debate_id=debate.id,
        speaker_id=str(evt.get("speaker_id") or debate.active_speaker_id or ""),
        speaker_name=str(evt.get("speaker_name") or ""),
        side=str(evt.get("side") or ""),
        phase=str(evt.get("phase") or debate.phase),
        segment_label=str(evt.get("segment_label") or debate.segment_label),
        content=content,
    )
    return _schedule_tts_audio_for_message(debate, message)


def _schedule_tts_audio(debate: DebateState) -> None:
    if not debate.messages:
        return
    message_id = debate.messages[-1].id
    if _schedule_tts_audio_for_message(debate, debate.messages[-1]):
        return

    async def run() -> None:
        try:
            doc = await get_debate(debate.id)
            if doc is None:
                return
            latest = DebateState.model_validate(doc)
            if not latest.tts_enabled:
                return
            await _attach_tts_audio(latest)
            updated = next((m for m in latest.messages if m.id == message_id), None)
            if not updated or not updated.audio_url:
                return
            await _persist_tts_message_audio(debate.id, updated)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("background TTS attach failed for debate %s message %s", debate.id, message_id)

    asyncio.create_task(run())


async def _attach_tts_audio_and_persist(debate: DebateState) -> float:
    if not debate.messages:
        return 0.5
    message_id = debate.messages[-1].id
    wait_sec = await _attach_tts_audio(debate)
    updated = next((m for m in debate.messages if m.id == message_id), None)
    if not updated or not updated.audio_url:
        return wait_sec
    await _persist_tts_message_audio(debate.id, updated)
    return wait_sec


async def _auto_loop(debate_id: str) -> None:
    async with _runner_lock(debate_id):
        while True:
            async with online_room_lock(debate_id):
                doc = await get_debate(debate_id)
                if doc is None:
                    break
                debate = DebateState.model_validate(doc)
                if debate.phase == "finished":
                    debate.auto_running = False
                    await _persist(debate)
                    await _broadcast_state(debate_id, "debate_finished", debate)
                    append_changelog(
                        f"辩论结束 · {debate.topic[:24]}",
                        f"房间 `{debate_id}` 已完成全部环节。正方 {debate.score.get('affirmative', 0):.1f} · 反方 {debate.score.get('negative', 0):.1f}",
                    )
                    break

                if needs_user_turn(debate):
                    prepare_next_online_user_turn(debate)
                    debate.awaiting_user = True
                    debate.auto_running = False
                    mark_user_wait_start(debate)
                    await _persist(debate)
                    await _broadcast_state(debate_id, "awaiting_user", debate)
                    append_changelog(
                        f"等待用户发言 · {debate.segment_label}",
                        f"房间 `{debate_id}` 当前环节需用户（{debate.mode.value}）输入。",
                    )
                    break

                debate.awaiting_user = False
                debate.auto_running = True
                playback_wait = 0.2
                schedule_tts_after_persist = False
                await _persist(debate)

            try:
                if is_procedural_segment(debate):
                    agent = next((item for item in debate.agents if item.id == debate.active_speaker_id), None)
                    await _broadcast(
                        debate_id,
                        "workflow_progress",
                        {
                            "type": "workflow_progress",
                            "node_id": debate.schedule[debate.schedule_index].id if debate.schedule else "",
                            "node_label": debate.segment_label,
                            "node_detail": debate.segment_rules,
                            "segment_label": debate.segment_label,
                            "phase": debate.phase,
                            "speaker_id": debate.active_speaker_id,
                            "speaker_name": agent.name if agent else "系统推进",
                            "side": agent.side if agent else "judge",
                            "position": agent.position if agent else 0,
                            "schedule_index": debate.schedule_index,
                            "schedule_total": len(debate.schedule or []),
                        },
                    )
                    debate = await _run_procedural_step(debate)
                else:
                    debate = await _run_turn_with_events(debate)
                    if debate.messages and should_synthesize_tts(debate, debate.messages[-1]):
                        schedule_tts_after_persist = True
                        playback_wait = 0.8
            except Exception as exc:
                logger.exception("auto turn failed: %s", exc)
                debate.auto_running = False
                async with online_room_lock(debate_id):
                    latest_doc = await get_debate(debate_id)
                    if latest_doc is not None:
                        _preserve_live_online_fields(debate, DebateState.model_validate(latest_doc))
                    await _persist(debate)
                    await _broadcast(debate_id, "error", {"message": str(exc)})
                break

            async with online_room_lock(debate_id):
                latest_doc = await get_debate(debate_id)
                if latest_doc is not None:
                    _preserve_live_online_fields(debate, DebateState.model_validate(latest_doc))
                await _persist(debate)
                await _broadcast_state(debate_id, "debate_stepped", debate)
                if schedule_tts_after_persist:
                    _schedule_tts_audio(debate)
                append_changelog(
                    f"AI 回合 · {debate.segment_label}",
                    f"房间 `{debate_id}` 完成一步；发言方 `{debate.active_speaker_id}`。",
                )

                if not debate.auto_running:
                    break

                if debate.phase == "finished":
                    debate.auto_running = False
                    await _persist(debate)
                    await _broadcast_state(debate_id, "debate_finished", debate)
                    break

            await asyncio.sleep(max(0.2, min(float(playback_wait), 35.0)))


def start_auto(debate_id: str) -> None:
    stop_auto(debate_id)
    task = asyncio.create_task(_auto_loop(debate_id))
    _tasks[debate_id] = task


def stop_auto(debate_id: str) -> None:
    task = _tasks.pop(debate_id, None)
    if task and not task.done():
        task.cancel()


def resume_auto(debate_id: str) -> None:
    if debate_id in _tasks and not _tasks[debate_id].done():
        return
    start_auto(debate_id)


def active_runner_status() -> dict[str, dict[str, str | bool]]:
    """管理端：当前内存中的自动推进任务状态。"""
    out: dict[str, dict[str, str | bool]] = {}
    for debate_id, task in list(_tasks.items()):
        out[debate_id] = {
            "running": not task.done(),
            "cancelled": task.cancelled(),
        }
    return out
