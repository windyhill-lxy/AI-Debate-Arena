"""WebSocket 集成测试：starlette TestClient 全链路（snapshot / 流式 / 推进广播）。"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def sync_client() -> TestClient:
    from app.main import app

    with TestClient(app) as client:
        yield client


def _create_debate(client: TestClient, *, schedule: str = "formal_4v4") -> str:
    r = client.post(
        "/api/debates",
        json={
            "topic": "WebSocket E2E",
            "mode": "ai_autonomous",
            "schedule_template": schedule,
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


def _advance_to_speaker_turn(client: TestClient, debate_id: str, max_steps: int = 40) -> None:
    """推进至正方/反方发言环节，便于 Mock LLM 产生 speech_* 事件。"""
    for _ in range(max_steps):
        doc = client.get(f"/api/debates/{debate_id}").json()
        if doc.get("phase") == "finished":
            break
        speaker = str(doc.get("active_speaker_id") or "")
        phase = str(doc.get("phase") or "")
        label = str(doc.get("segment_label") or "")
        is_public_speech = phase not in {"opening_prep", "free_prep", "closing_prep"} and not any(
            marker in label for marker in ("任务分配", "队内讨论", "真实论据入库")
        )
        if speaker.startswith(("aff_", "neg_")) and is_public_speech:
            return
        step = client.post(f"/api/debates/{debate_id}/step")
        if step.status_code != 200:
            break


def _ws_event_name(payload: dict) -> str:
    return str(payload.get("event") or payload.get("type") or "")


def _drain_ws(ws, *, stop_on: str | set[str] | None = None, max_messages: int = 80) -> list[str]:
    names: list[str] = []
    stop_set = {stop_on} if isinstance(stop_on, str) else (set(stop_on) if stop_on else None)
    for _ in range(max_messages):
        try:
            payload = ws.receive_json()
        except Exception:
            break
        name = _ws_event_name(payload)
        names.append(name)
        if stop_set and name in stop_set:
            break
    return names


def test_websocket_snapshot_on_connect(sync_client: TestClient) -> None:
    debate_id = _create_debate(sync_client)
    with sync_client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws:
        msg = ws.receive_json()
    assert msg["event"] == "snapshot"
    assert msg["debate"]["id"] == debate_id
    assert msg["debate"]["topic"] == "WebSocket E2E"


def test_websocket_unknown_debate_still_accepts(sync_client: TestClient) -> None:
    """无效房间 ID 仍建立连接，但不推送 snapshot。"""
    with sync_client.websocket_connect("/api/debates/ws/nonexistent-id") as ws:
        ws.send_text("ping")


def test_websocket_receives_debate_stepped(sync_client: TestClient, mock_llm_stream: None) -> None:
    debate_id = _create_debate(sync_client)
    _advance_to_speaker_turn(sync_client, debate_id)

    with sync_client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws:
        assert ws.receive_json()["event"] == "snapshot"
        step = sync_client.post(f"/api/debates/{debate_id}/step")
        assert step.status_code == 200
        events = _drain_ws(ws, stop_on="debate_stepped")

    assert "debate_stepped" in events


def test_websocket_speech_stream_events(sync_client: TestClient, mock_llm_stream: None) -> None:
    debate_id = _create_debate(sync_client)
    _advance_to_speaker_turn(sync_client, debate_id)

    with sync_client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws:
        assert ws.receive_json()["event"] == "snapshot"
        sync_client.post(f"/api/debates/{debate_id}/step")
        events = _drain_ws(ws, stop_on="debate_stepped")

    assert {"speech_start", "speech_chunk", "speech_end"}.issubset(set(events))


def test_websocket_reconnect_gets_fresh_snapshot(sync_client: TestClient) -> None:
    debate_id = _create_debate(sync_client)
    with sync_client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws:
        first = ws.receive_json()
    assert first["event"] == "snapshot"

    with sync_client.websocket_connect(f"/api/debates/ws/{debate_id}") as ws2:
        second = ws2.receive_json()
    assert second["event"] == "snapshot"
    assert second["debate"]["id"] == debate_id


def test_share_meta_endpoint(sync_client: TestClient) -> None:
    debate_id = _create_debate(sync_client)
    r = sync_client.get(f"/api/debates/{debate_id}/share")
    assert r.status_code == 200
    body = r.json()
    assert body["readonly"] is True
    assert body["path"] == f"/share/{debate_id}"
    assert body["debate_id"] == debate_id
