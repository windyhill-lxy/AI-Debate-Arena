"""联机席位 presence：WS 重连恢复、延迟离线、多标签。"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def fast_offline_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.presence.OFFLINE_GRACE_SECONDS", 0.15)


def _wait_participant_connected(
    client: TestClient,
    debate_id: str,
    participant_id: str,
    *,
    expected: bool,
    timeout: float = 2.0,
) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        doc = client.get(f"/api/debates/{debate_id}").json()
        participant = next(p for p in doc["participants"] if p["id"] == participant_id)
        if participant["connected"] is expected:
            return
        time.sleep(0.05)
    assert participant["connected"] is expected


@pytest.fixture
def sync_client() -> TestClient:
    from app.main import app
    from app.services import presence
    from app.services.realtime import manager

    presence.reset_presence_tasks()
    manager.active.clear()
    with TestClient(app) as client:
        yield client
    presence.reset_presence_tasks()
    manager.active.clear()


def _create_online_room(client: TestClient) -> tuple[str, str]:
    create = client.post(
        "/api/debates",
        json={"topic": "presence 测试", "mode": "online_match", "schedule_template": "formal_4v4"},
    )
    assert create.status_code == 200
    debate_id = create.json()["id"]
    join = client.post(
        f"/api/debates/{debate_id}/participants",
        json={"name": "正方一辩", "side": "affirmative", "position": 1},
    )
    assert join.status_code == 200
    participant_id = join.json()["participant"]["id"]
    return debate_id, participant_id


def test_ws_connect_restores_participant_connected(sync_client: TestClient) -> None:
    debate_id, participant_id = _create_online_room(sync_client)
    doc = sync_client.get(f"/api/debates/{debate_id}").json()
    assert any(p["id"] == participant_id and p["connected"] for p in doc["participants"])

    with sync_client.websocket_connect(
        f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
    ) as ws:
        msg = ws.receive_json()
        assert msg["event"] == "snapshot"

    doc = sync_client.get(f"/api/debates/{debate_id}").json()
    participant = next(p for p in doc["participants"] if p["id"] == participant_id)
    assert participant["connected"] is True


def test_ws_disconnect_delayed_offline(sync_client: TestClient) -> None:
    debate_id, participant_id = _create_online_room(sync_client)
    with sync_client.websocket_connect(
        f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
    ) as ws:
        ws.receive_json()

    doc = sync_client.get(f"/api/debates/{debate_id}").json()
    participant = next(p for p in doc["participants"] if p["id"] == participant_id)
    assert participant["connected"] is True

    _wait_participant_connected(
        sync_client, debate_id, participant_id, expected=False
    )


def test_ws_reconnect_before_grace_keeps_connected(sync_client: TestClient) -> None:
    debate_id, participant_id = _create_online_room(sync_client)
    with sync_client.websocket_connect(
        f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
    ) as ws:
        ws.receive_json()

    import time

    time.sleep(0.5)

    with sync_client.websocket_connect(
        f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
    ) as ws2:
        ws2.receive_json()

    _wait_participant_connected(
        sync_client, debate_id, participant_id, expected=True
    )


def test_multi_tab_same_participant_no_premature_offline(sync_client: TestClient) -> None:
    debate_id, participant_id = _create_online_room(sync_client)
    with sync_client.websocket_connect(
        f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
    ) as ws1:
        ws1.receive_json()
        with sync_client.websocket_connect(
            f"/api/debates/ws/{debate_id}?participant_id={participant_id}"
        ) as ws2:
            ws2.receive_json()

    _wait_participant_connected(
        sync_client, debate_id, participant_id, expected=True
    )
