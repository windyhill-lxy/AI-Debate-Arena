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
async def test_online_room_create_starts_opening_evidence_warmup(client: AsyncClient, monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr("app.api.debates.warm_opening_evidence", lambda debate: calls.append(debate.id))
    create = await client.post(
        "/api/debates",
        json={"topic": "联机论据预热", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]

    assert create.status_code == 200
    assert calls == [debate_id]


@pytest.mark.asyncio
async def test_online_ready_and_guest_join_do_not_restart_opening_evidence_warmup(client: AsyncClient, monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr("app.api.debates.warm_opening_evidence", lambda debate: calls.append(debate.id))
    create = await client.post(
        "/api/debates",
        json={"topic": "宾客选座论据预热", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    token = create.json()["host_token"]
    await client.post(f"/api/debates/{debate_id}/online-ready", headers={"x-host-token": token})

    join = await client.post(
        f"/api/debates/{debate_id}/participants",
        json={"participant_id": "guest-1", "name": "正方一辩", "side": "affirmative", "position": 1},
    )

    assert join.status_code == 200
    assert calls == [debate_id]


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


@pytest.mark.asyncio
async def test_online_match_rejects_duplicate_connected_seat(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "联机抢席测试", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    host_token = create.json()["host_token"]

    first = await client.post(
        f"/api/debates/{debate_id}/participants",
        json={"participant_id": "p1", "name": "正方一辩甲", "side": "affirmative", "position": 1},
    )
    assert first.status_code == 200
    ready = await client.post(
        f"/api/debates/{debate_id}/online-ready",
        headers={"x-host-token": host_token},
    )
    assert ready.status_code == 200

    second = await client.post(
        f"/api/debates/{debate_id}/participants",
        json={"participant_id": "p2", "name": "正方一辩乙", "side": "affirmative", "position": 1},
    )
    assert second.status_code == 409
    assert "占用" in str(second.json())
