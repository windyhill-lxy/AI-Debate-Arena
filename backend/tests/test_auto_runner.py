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
