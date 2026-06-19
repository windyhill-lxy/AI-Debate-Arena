from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.time_utils import utc_now
from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.speech_timeout import apply_timeout_penalty_if_needed


@pytest.mark.asyncio
async def test_ai_autonomous_forces_all_visible_and_locks_rules(client: AsyncClient) -> None:
    created = await client.post(
        "/api/debates",
        json={
            "topic": "可见性测试",
            "mode": "ai_autonomous",
            "visibility": "own_side_only",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["visibility"] == "all_visible"
    assert body["visibility_locked"] is True
    assert body["human_timeout_penalty_enabled"] is False


@pytest.mark.asyncio
async def test_human_room_keeps_prestart_visibility_and_locks_it(client: AsyncClient) -> None:
    created = await client.post(
        "/api/debates",
        json={
            "topic": "人类可见性测试",
            "mode": "user_affirmative",
            "visibility": "own_side_only",
            "timing": "limited",
            "turn_seconds": 30,
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["visibility"] == "own_side_only"
    assert body["visibility_locked"] is True
    assert body["timing_locked"] is True
    assert body["human_timeout_penalty_enabled"] is True


def test_timeout_penalty_applies_once_for_late_human_speech() -> None:
    debate = DebateState(
        topic="超时扣分测试",
        mode=DebateMode.user_affirmative,
        visibility=DebateVisibility.own_side_only,
        timing=DebateTiming.limited,
        turn_seconds=30,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        awaiting_user=True,
        awaiting_user_since=utc_now() - timedelta(seconds=45),
    )

    delta, reason = apply_timeout_penalty_if_needed(debate, "affirmative", now=utc_now())
    assert delta == pytest.approx(-0.5)
    assert "超时" in reason
    assert debate.score["affirmative"] == pytest.approx(-0.5)

    second_delta, _ = apply_timeout_penalty_if_needed(debate, "affirmative", now=utc_now())
    assert second_delta == 0
    assert debate.score["affirmative"] == pytest.approx(-0.5)
