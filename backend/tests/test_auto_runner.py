import pytest

from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template


def _ai_public_debate() -> DebateState:
    return DebateState(
        topic="auto runner lock test",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        phase="opening_statement",
        segment_label="正方一辩立论",
        active_speaker_id="aff_1",
        auto_running=True,
    )


@pytest.mark.asyncio
async def test_auto_runner_releases_room_lock_while_generating_turn(monkeypatch) -> None:
    from app.services import auto_runner
    from app.services.online_room_lock import online_room_lock

    debate = _ai_public_debate()
    lock_states: list[bool] = []

    async def fake_get_debate(_debate_id: str):
        return debate.model_dump(mode="json")

    async def fake_run_turn_with_events(current: DebateState) -> DebateState:
        lock_states.append(online_room_lock(current.id).locked())
        current.phase = "finished"
        current.auto_running = False
        return current

    async def noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auto_runner, "get_debate", fake_get_debate)
    monkeypatch.setattr(auto_runner, "_run_turn_with_events", fake_run_turn_with_events)
    monkeypatch.setattr(auto_runner, "_persist", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast_state", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast", noop_async)
    monkeypatch.setattr(auto_runner, "cache_publish", noop_async)
    monkeypatch.setattr(auto_runner, "append_changelog", lambda *_args, **_kwargs: None)

    await auto_runner._auto_loop(debate.id)

    assert lock_states == [False]


@pytest.mark.asyncio
async def test_run_turn_starts_tts_as_soon_as_speech_stream_ends(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    debate = _ai_public_debate()
    events: list[str] = []

    async def fake_run_turn_streaming(current: DebateState, *, on_event):
        events.append("turn-start")
        await on_event(
            {
                "type": "speech_end",
                "message_id": "msg-fast-tts",
                "content": "LLM 刚输出完的最终发言。",
                "speaker_id": "aff_1",
                "speaker_name": "正方一辩",
                "side": "affirmative",
                "phase": "opening_statement",
                "segment_label": "正方一辩立论",
            }
        )
        events.append("after-speech-end")
        current.messages.append(
            DebateMessage(
                id="msg-fast-tts",
                debate_id=current.id,
                speaker_id="aff_1",
                speaker_name="正方一辩",
                side="affirmative",
                phase="opening_statement",
                segment_label="正方一辩立论",
                content="LLM 刚输出完的最终发言。",
            )
        )
        return current

    def fake_schedule_tts_audio_for_message(_debate: DebateState, message: DebateMessage) -> bool:
        events.append(f"tts-started:{message.id}:{message.content}")
        return True

    async def noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auto_runner.debate_graph, "run_turn_streaming", fake_run_turn_streaming)
    monkeypatch.setattr(auto_runner, "_schedule_tts_audio_for_message", fake_schedule_tts_audio_for_message, raising=False)
    monkeypatch.setattr(auto_runner, "_broadcast_debate_event", noop_async)

    await auto_runner._run_turn_with_events(debate)

    assert events == [
        "turn-start",
        "tts-started:msg-fast-tts:LLM 刚输出完的最终发言。",
        "after-speech-end",
    ]


@pytest.mark.asyncio
async def test_auto_runner_schedules_tts_without_blocking_turn_progress(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    debate = _ai_public_debate()
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="云汐",
            side="affirmative",
            phase="opening_statement",
            segment_label="正方一辩立论",
            content="测试发言",
        )
    )
    events: list[str] = []
    real_sleep = auto_runner.asyncio.sleep

    async def fake_get_debate(_debate_id: str):
        return debate.model_dump(mode="json")

    async def fake_run_turn_with_events(current: DebateState) -> DebateState:
        events.append("turn")
        current.auto_running = True
        current.phase = "opening_statement"
        return current

    def fake_schedule_tts_audio(_debate: DebateState) -> None:
        events.append("tts-scheduled")

    async def fake_sleep(_seconds: float) -> None:
        assert "tts-scheduled" in events
        events.append("sleep")
        debate.phase = "finished"
        debate.auto_running = False

    async def noop_async(*_args, **_kwargs):
        return None

    async def fake_persist(_debate: DebateState) -> None:
        events.append("persist")

    async def fake_broadcast_state(*_args, **_kwargs):
        events.append("broadcast")

    monkeypatch.setattr(auto_runner, "get_debate", fake_get_debate)
    monkeypatch.setattr(auto_runner, "_run_turn_with_events", fake_run_turn_with_events)
    monkeypatch.setattr(auto_runner, "_schedule_tts_audio", fake_schedule_tts_audio)
    monkeypatch.setattr(auto_runner, "_persist", fake_persist)
    monkeypatch.setattr(auto_runner, "_broadcast_state", fake_broadcast_state)
    monkeypatch.setattr(auto_runner, "_broadcast", noop_async)
    monkeypatch.setattr(auto_runner, "cache_publish", noop_async)
    monkeypatch.setattr(auto_runner, "append_changelog", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auto_runner.asyncio, "sleep", fake_sleep)

    await auto_runner._auto_loop(debate.id)

    assert events.index("tts-scheduled") > events.index("broadcast")
    assert events.index("sleep") > events.index("tts-scheduled")


@pytest.mark.asyncio
async def test_post_persist_tts_scheduler_reuses_early_speech_end_audio(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    debate = _ai_public_debate()
    message = DebateMessage(
        id="msg-early-result",
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="正方一辩",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="已经提前合成过的内容。",
    )
    debate.messages.append(message)
    early = message.model_copy(deep=True)
    early.audio_url = "/audio/msg-early-result.mp3"
    early.audio_urls = [early.audio_url]
    early.tts_voice = "Serena"
    early.tts_instructions = "clear"
    events: list[str] = []

    async def completed() -> None:
        return None

    task = auto_runner.asyncio.create_task(completed())
    await task
    key = (debate.id, message.id)
    monkeypatch.setitem(auto_runner._tts_message_tasks, key, task)
    monkeypatch.setitem(auto_runner._tts_message_results, key, early)

    async def fake_persist_tts_message_audio(_debate_id: str, source_message: DebateMessage) -> bool:
        events.append(f"persist-audio:{source_message.audio_url}")
        return True

    monkeypatch.setattr(auto_runner, "_persist_tts_message_audio", fake_persist_tts_message_audio)

    auto_runner._schedule_tts_audio(debate)
    await auto_runner.asyncio.sleep(0)

    assert message.audio_url == "/audio/msg-early-result.mp3"
    assert events == ["persist-audio:/audio/msg-early-result.mp3"]


@pytest.mark.asyncio
async def test_post_persist_tts_scheduler_does_not_duplicate_running_early_tts(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    debate = _ai_public_debate()
    message = DebateMessage(
        id="msg-running-early",
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="正方一辩",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="正在提前合成的内容。",
    )
    debate.messages.append(message)
    events: list[str] = []

    async def still_running() -> None:
        await auto_runner.asyncio.sleep(10)

    task = auto_runner.asyncio.create_task(still_running())
    monkeypatch.setitem(auto_runner._tts_message_tasks, (debate.id, message.id), task)

    def fake_create_task(_coro):
        events.append("duplicate-task")
        raise AssertionError("post-persist scheduler should not create duplicate TTS task")

    monkeypatch.setattr(auto_runner.asyncio, "create_task", fake_create_task)

    auto_runner._schedule_tts_audio(debate)

    task.cancel()
    with pytest.raises(auto_runner.asyncio.CancelledError):
        await task
    assert events == []


@pytest.mark.asyncio
async def test_post_persist_tts_scheduler_retries_after_failed_early_tts(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    debate = _ai_public_debate()
    message = DebateMessage(
        id="msg-retry-after-failure",
        debate_id=debate.id,
        speaker_id="aff_1",
        speaker_name="正方一辩",
        side="affirmative",
        phase="opening_statement",
        segment_label="正方一辩立论",
        content="第一次提前合成失败后需要重试。",
    )
    debate.messages.append(message)
    events: list[str] = []

    async def failed() -> None:
        raise RuntimeError("early tts failed")

    failed_task = auto_runner.asyncio.create_task(failed())
    with pytest.raises(RuntimeError):
        await failed_task
    monkeypatch.setitem(auto_runner._tts_message_tasks, (debate.id, message.id), failed_task)

    async def fake_attach_tts_audio_to_message(_debate: DebateState, target_message: DebateMessage) -> float:
        events.append("fallback-tts")
        target_message.audio_url = "/audio/retry.mp3"
        return 1.0

    async def fake_persist_tts_message_audio(_debate_id: str, source_message: DebateMessage) -> bool:
        events.append(f"persist-audio:{source_message.audio_url}")
        return True

    monkeypatch.setattr(auto_runner, "_attach_tts_audio_to_message", fake_attach_tts_audio_to_message)
    monkeypatch.setattr(auto_runner, "_persist_tts_message_audio", fake_persist_tts_message_audio)
    monkeypatch.setattr(auto_runner, "get_debate", lambda _debate_id: debate.model_dump(mode="json"))

    auto_runner._schedule_tts_audio(debate)
    await auto_runner.asyncio.sleep(0)

    assert events == ["fallback-tts", "persist-audio:/audio/retry.mp3"]


@pytest.mark.asyncio
async def test_auto_runner_synthesizes_unsaved_judge_opening(monkeypatch) -> None:
    from app.models import DebateMessage
    from app.services import auto_runner

    stored = _ai_public_debate()
    stored.messages = []

    current = stored.model_copy(deep=True)
    current.messages.append(
        DebateMessage(
            debate_id=current.id,
            speaker_id="judge",
            speaker_name="紫苑裁判",
            side="judge",
            phase="pre_match",
            segment_label="赛前准备 · 主持开场",
            content="欢迎进入本场辩论。",
        )
    )

    async def fake_get_debate(_debate_id: str):
        return stored.model_dump(mode="json")

    async def fake_synthesize_message_audio(message, _agent, on_chunk=None, on_audio_delta=None):
        if on_chunk:
            await on_chunk(1, 1)
        return {
            "audio_url": f"/audio/{message.id}.mp3",
            "audio_urls": [f"/audio/{message.id}.mp3"],
            "voice": "Serena",
            "instructions": "neutral",
            "expires_at": "2030-01-01T00:00:00Z",
            "playback_wait_sec": 1.0,
        }

    async def noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auto_runner, "get_debate", fake_get_debate)
    monkeypatch.setattr(auto_runner, "synthesize_message_audio", fake_synthesize_message_audio)
    monkeypatch.setattr(auto_runner, "_persist", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast_state", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast_debate_event", noop_async)

    wait = await auto_runner._attach_tts_audio_and_persist(current)

    assert wait == 1.0
    assert current.messages[-1].audio_url == f"/audio/{current.messages[-1].id}.mp3"
