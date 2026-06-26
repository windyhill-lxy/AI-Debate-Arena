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
async def test_auto_runner_waits_for_tts_before_playback_sleep(monkeypatch) -> None:
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

    async def fake_attach_tts_audio(_debate: DebateState) -> float:
        events.append("tts-start")
        await real_sleep(0.01)
        events.append("tts-end")
        debate.phase = "finished"
        debate.auto_running = False
        return 0.2

    async def fake_sleep(_seconds: float) -> None:
        assert "tts-end" in events
        events.append("sleep")

    async def noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auto_runner, "get_debate", fake_get_debate)
    monkeypatch.setattr(auto_runner, "_run_turn_with_events", fake_run_turn_with_events)
    monkeypatch.setattr(auto_runner, "_attach_tts_audio", fake_attach_tts_audio)
    monkeypatch.setattr(auto_runner, "_persist", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast_state", noop_async)
    monkeypatch.setattr(auto_runner, "_broadcast", noop_async)
    monkeypatch.setattr(auto_runner, "cache_publish", noop_async)
    monkeypatch.setattr(auto_runner, "append_changelog", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auto_runner.asyncio, "sleep", fake_sleep)

    await auto_runner._auto_loop(debate.id)

    assert events[:4] == ["turn", "tts-start", "tts-end", "sleep"]


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

    async def fake_synthesize_message_audio(message, _agent, on_chunk=None):
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
