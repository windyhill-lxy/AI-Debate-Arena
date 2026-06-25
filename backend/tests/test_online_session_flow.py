"""公网 session 邀请状态机：waiting -> preparing -> ready。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_online_session_state_machine(client: AsyncClient) -> None:
    session = await client.post("/api/debates/online-session")
    assert session.status_code == 200
    session_id = session.json()["session_id"]

    waiting = await client.get(f"/api/debates/online-session/{session_id}")
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "waiting"
    assert waiting.json()["debate_id"] is None

    create = await client.post(
        "/api/debates",
        json={
            "topic": "session 流程测试",
            "mode": "online_match",
            "schedule_template": "formal_4v4",
            "session_id": session_id,
        },
    )
    assert create.status_code == 200
    debate_id = create.json()["id"]
    host_token = create.json()["host_token"]

    preparing = await client.get(f"/api/debates/online-session/{session_id}")
    assert preparing.status_code == 200
    body = preparing.json()
    assert body["status"] == "preparing"
    assert body["debate_id"] == debate_id
    assert body["online_ready"] is False

    ready_resp = await client.post(
        f"/api/debates/{debate_id}/online-ready",
        headers={"x-host-token": host_token},
    )
    assert ready_resp.status_code == 200

    ready = await client.get(f"/api/debates/online-session/{session_id}")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["online_ready"] is True
    assert ready.json()["debate_id"] == debate_id

    join = await client.post(
        f"/api/debates/{debate_id}/participants",
        json={"name": "反方一辩", "side": "negative", "position": 1},
    )
    assert join.status_code == 200
    assert join.json()["participant"]["connected"] is True
