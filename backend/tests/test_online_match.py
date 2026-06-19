import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_online_match_host_token_issued(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "联机 token 测试", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    assert create.status_code == 200
    body = create.json()
    assert body.get("host_token")
    assert body["mode"] == "online_match"


@pytest.mark.asyncio
async def test_online_ready_requires_host_token(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "联机就绪鉴权", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    denied = await client.post(f"/api/debates/{debate_id}/online-ready")
    assert denied.status_code == 403

    token = create.json()["host_token"]
    ok = await client.post(
        f"/api/debates/{debate_id}/online-ready",
        headers={"x-host-token": token},
    )
    assert ok.status_code == 200
    assert ok.json()["online_ready"] is True


@pytest.mark.asyncio
async def test_online_match_user_turn_allowed_in_snapshot(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "联机回合字段", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    join = await client.post(
        f"/api/debates/{debate_id}/participants",
        json={"name": "正方一辩", "side": "affirmative", "position": 1},
    )
    participant_id = join.json()["participant"]["id"]
    state = (
        await client.get(
            f"/api/debates/{debate_id}",
            params={"participant_id": participant_id},
        )
    ).json()
    assert "user_turn_allowed" in state
    assert isinstance(state["user_turn_allowed"], bool)
