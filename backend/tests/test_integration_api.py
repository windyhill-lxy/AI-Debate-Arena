"""HTTP 集成测试：创建房间、管理端、恢复推进。"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _force_user_turn(debate_id: str, speaker_id: str = "aff_3") -> dict:
    from app.db.mongo import get_debate, save_debate

    doc = await get_debate(debate_id)
    assert doc is not None
    doc["phase"] = "opening_statement"
    doc["schedule_index"] = 10
    doc["segment_label"] = "正方三辩发言"
    doc["segment_rules"] = "用户测试发言"
    doc["active_speaker_id"] = speaker_id
    doc["awaiting_user"] = True
    doc["auto_running"] = False
    await save_debate(doc)
    return doc


async def _force_aff_team_discussion_turn(debate_id: str, *, fill_argument_bank: bool) -> dict:
    from app.db.mongo import get_debate, save_debate
    from app.models import ArgumentBankItem, DebateState
    from app.services.debate_schedule import apply_segment, get_segment

    doc = await get_debate(debate_id)
    assert doc is not None
    debate = DebateState.model_validate(doc)
    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")
    debate.awaiting_user = True
    debate.auto_running = False
    if fill_argument_bank:
        debate.argument_bank_locked = True
        debate.argument_bank["affirmative"] = [
            ArgumentBankItem(
                id=f"AFF-{index}",
                side="affirmative",
                title=f"正方事实{index}",
                claim=f"202{index % 10}年机构报告显示正方事实{index}。",
            )
            for index in range(1, 11)
        ]
        debate.argument_bank["negative"] = [
            ArgumentBankItem(
                id=f"NEG-{index}",
                side="negative",
                title=f"反方事实{index}",
                claim=f"202{index % 10}年机构报告显示反方事实{index}。",
            )
            for index in range(1, 11)
        ]
    await save_debate(debate.model_dump(mode="json"))
    return debate.model_dump(mode="json")


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "storage" in body
    assert "deepseek_configured" in body


@pytest.mark.asyncio
async def test_create_and_get_debate(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "集成测试辩题",
            "mode": "ai_autonomous",
            "schedule_template": "formal_4v4",
        },
    )
    assert create.status_code == 200
    debate = create.json()
    assert debate["topic"] == "集成测试辩题"
    assert debate["id"]
    assert debate["auto_running"] is True

    get_r = await client.get(f"/api/debates/{debate['id']}")
    assert get_r.status_code == 200
    assert get_r.json()["id"] == debate["id"]


@pytest.mark.asyncio
async def test_http_error_has_popup_ready_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/debates/not-found-id")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["message"] == "Debate not found"
    assert body["error"]["code"] == "http_error"
    assert body["error"]["status"] == 404
    assert body["error"]["request_id"]


@pytest.mark.asyncio
async def test_create_debate_materials_immediately_populate_argument_bank(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "人工智能是否会提升青少年的综合学习能力",
            "mode": "ai_autonomous",
            "schedule_template": "formal_4v4",
            "materials": [
                {
                    "title": "韩国AI作业禁令",
                    "content": "2024年韩国教育部门限制小学生用 AI 完成家庭作业，担心学生主动思考能力下降。",
                }
            ],
        },
    )

    assert create.status_code == 200
    debate = create.json()
    assert any(item["title"] == "韩国AI作业禁令" for item in debate["argument_bank"]["negative"])


@pytest.mark.asyncio
async def test_create_user_affirmative_mode(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "人机测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    assert create.status_code == 200
    debate = create.json()
    assert debate["mode"] == "user_affirmative"
    assert debate["active_speaker_id"] == "judge"


@pytest.mark.asyncio
async def test_create_user_mode_renames_configured_seat_only(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "人机席位测试",
            "mode": "user_negative",
            "user_side": "negative",
            "user_position": 4,
            "user_name": "小明四辩",
            "schedule_template": "formal_4v4",
        },
    )
    assert create.status_code == 200
    debate = create.json()
    assert debate["user_side"] == "negative"
    assert debate["user_position"] == 4
    assert debate["user_name"] == "小明四辩"

    agents = {agent["id"]: agent["name"] for agent in debate["agents"]}
    assert agents["neg_4"] == "小明四辩"
    assert agents["neg_1"] != "小明四辩"


@pytest.mark.asyncio
async def test_user_mode_message_then_resume(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "人机流程测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    assert create.status_code == 200
    debate = create.json()
    debate_id = debate["id"]

    force_user_turn = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "用户辩手",
            "side": "affirmative",
            "content": "我方认为 AI 在个性化反馈方面能提升学习效率。",
        },
    )
    # 初始 formal_4v4 为裁判环节，不允许直接用户发言。
    assert force_user_turn.status_code == 400

    step = await client.post(f"/api/debates/{debate_id}/step")
    assert step.status_code == 200
    stepped = step.json()
    assert stepped["active_speaker_id"] == "aff_1"

    submit = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "用户辩手",
            "side": "affirmative",
            "content": "我方主张：AI 提供即时反馈和错题闭环，能提升学习能力。",
        },
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["awaiting_user"] is False
    assert len(body["messages"]) >= 2

    resumed = await client.post(f"/api/debates/{debate_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_user_message_uses_configured_debater_seat(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "用户三辩发言测试",
            "mode": "user_affirmative",
            "user_side": "affirmative",
            "user_position": 3,
            "user_name": "用户三辩",
            "schedule_template": "formal_4v4",
        },
    )
    debate_id = create.json()["id"]

    await _force_user_turn(debate_id, "aff_3")

    submit = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "错误名称",
            "side": "affirmative",
            "position": 1,
            "content": "我方三辩指出，对方忽视了学习能力需要长期训练和验证。",
        },
    )
    assert submit.status_code == 200
    message = submit.json()["messages"][-1]
    assert message["speaker_id"] == "aff_3"
    assert message["speaker_name"] == "用户三辩"


@pytest.mark.asyncio
async def test_assist_routes_pass_configured_user_position(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "辅助席位透传测试",
            "mode": "user_affirmative",
            "user_side": "affirmative",
            "user_position": 2,
            "user_name": "用户二辩",
            "schedule_template": "formal_4v4",
        },
    )
    debate_id = create.json()["id"]

    with patch(
        "app.api.debates.generate_assist",
        new_callable=AsyncMock,
        return_value={"side": "affirmative", "position": 2, "suggestion": "ok", "sources": []},
    ) as mocked:
        response = await client.post(
            f"/api/debates/{debate_id}/assist",
            json={"side": "affirmative", "position": 2, "draft": "请按二辩给建议"},
        )

    assert response.status_code == 200
    mocked.assert_awaited_once()
    assert mocked.await_args.args[1:] == ("affirmative", "请按二辩给建议", 2)


@pytest.mark.asyncio
async def test_draft_stream_route_passes_user_position(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={
            "topic": "流式代拟席位透传测试",
            "mode": "user_affirmative",
            "user_side": "affirmative",
            "user_position": 2,
            "user_name": "用户二辩",
            "schedule_template": "formal_4v4",
        },
    )
    debate_id = create.json()["id"]
    calls = []

    async def fake_stream(debate, side: str, draft: str, position: int):
        calls.append((debate.id, side, draft, position))
        yield {"type": "done", "data": {"side": side, "position": position, "draft": "二辩草稿 [AFF-1]"}}

    with patch("app.api.debates.generate_draft_stream_events", new=fake_stream):
        response = await client.post(
            f"/api/debates/{debate_id}/assist/draft/stream",
            json={"side": "affirmative", "position": 2, "draft": "请按二辩代拟"},
        )

    assert response.status_code == 200
    assert calls == [(debate_id, "affirmative", "请按二辩代拟", 2)]
    assert '"position": 2' in response.text


@pytest.mark.asyncio
async def test_public_low_information_user_message_triggers_judge_warning(client: AsyncClient) -> None:
    from app.services.user_speech_judge import UserSpeechReview

    create = await client.post(
        "/api/debates",
        json={
            "topic": "公开灌水测试",
            "mode": "user_affirmative",
            "user_side": "affirmative",
            "user_position": 3,
            "user_name": "用户三辩",
            "schedule_template": "formal_4v4",
        },
    )
    debate_id = create.json()["id"]

    await _force_user_turn(debate_id, "aff_3")

    before = (await client.get(f"/api/debates/{debate_id}")).json()
    reject = UserSpeechReview(
        acceptable=False,
        reason="灌水",
        penalty=0.5,
        judge_comment="裁判警告：本轮发言信息量不足，扣0.5分，请重新发言。",
    )
    with patch(
        "app.api.debates.review_user_speech",
        new_callable=AsyncMock,
        return_value=reject,
    ):
        bad = await client.post(
            f"/api/debates/{debate_id}/message",
            json={
                "speaker_id": "aff_3",
                "speaker_name": "用户三辩",
                "side": "affirmative",
                "content": "嗯嗯嗯嗯嗯",
            },
        )
    assert bad.status_code == 200
    body = bad.json()
    assert body["awaiting_user"] is False
    assert body["schedule_index"] > before["schedule_index"]
    assert body["score"]["affirmative"] == pytest.approx(before["score"]["affirmative"] - 0.5)
    stored = body["messages"][-1]
    assert stored["side"] == "affirmative"
    assert stored["speech_flag"] == "inappropriate"
    assert stored["content"] == "嗯嗯嗯嗯嗯"
    assert stored["score_delta"] == -0.5


@pytest.mark.asyncio
async def test_internal_low_information_user_message_triggers_teammate_reminder(client: AsyncClient) -> None:
    from app.services.user_speech_judge import UserSpeechReview

    create = await client.post(
        "/api/debates",
        json={"topic": "队内灌水测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    await client.post(f"/api/debates/{debate_id}/step")
    before = (await client.get(f"/api/debates/{debate_id}")).json()

    reject = UserSpeechReview(
        acceptable=False,
        reason="无效队内讨论",
        teammate_comment="队友提醒：请围绕任务分工重新输出，不要灌水。",
    )
    with patch(
        "app.api.debates.review_user_speech",
        new_callable=AsyncMock,
        return_value=reject,
    ):
        bad = await client.post(
            f"/api/debates/{debate_id}/message",
            json={
                "speaker_id": "aff_1",
                "speaker_name": "用户辩手",
                "side": "affirmative",
                "content": "字母字母字母字母字母字母",
            },
        )
    assert bad.status_code == 200
    body = bad.json()
    assert body["awaiting_user"] is False
    assert body["schedule_index"] > before["schedule_index"]
    assert body["score"] == before["score"]
    stored = body["messages"][-1]
    assert stored["side"] == "affirmative"
    assert stored["speech_flag"] == "inappropriate"
    assert "字母字母" in stored["content"]


@pytest.mark.asyncio
async def test_user_can_post_once_during_team_discussion_segment(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "队内讨论禁言测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    state = await _force_aff_team_discussion_turn(debate_id, fill_argument_bank=True)

    first = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "用户辩手",
            "side": "affirmative",
            "content": "队内讨论：我补充一条分工，二辩守定义。",
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["phase"] == state["phase"]
    assert first_body["schedule_index"] == state["schedule_index"]
    assert first_body["awaiting_user"] is False

    blocked = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "用户辩手",
            "side": "affirmative",
            "content": "我又说了一遍，这不应该被接受。",
        },
    )
    assert blocked.status_code == 400


@pytest.mark.asyncio
async def test_team_discussion_rejects_user_before_opening_argument_bank_ready(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "队内讨论论据门禁测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    await _force_aff_team_discussion_turn(debate_id, fill_argument_bank=False)

    blocked = await client.post(
        f"/api/debates/{debate_id}/message",
        json={
            "speaker_id": "aff_1",
            "speaker_name": "用户辩手",
            "side": "affirmative",
            "content": "队内讨论：我现在先说分工。",
        },
    )

    assert blocked.status_code == 409
    assert "论据库" in blocked.text
    state = (await client.get(f"/api/debates/{debate_id}")).json()
    assert state["awaiting_user"] is False
    assert state["auto_running"] is True
    assert state["opening_argument_bank_ready"] is False
    assert state["user_turn_allowed"] is False


@pytest.mark.asyncio
async def test_get_debate_filters_opponent_internal_discussion(client: AsyncClient) -> None:
    from app.services.user_speech_judge import UserSpeechReview

    create = await client.post(
        "/api/debates",
        json={"topic": "接口隔离测试", "mode": "user_affirmative", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]
    await client.post(f"/api/debates/{debate_id}/step")
    reject = UserSpeechReview(
        acceptable=False,
        reason="无效队内讨论",
        teammate_comment="队友提醒：请围绕任务分工重新输出，不要灌水。",
    )
    with patch(
        "app.api.debates.review_user_speech",
        new_callable=AsyncMock,
        return_value=reject,
    ):
        bad = await client.post(
            f"/api/debates/{debate_id}/message",
            json={
                "speaker_id": "aff_1",
                "speaker_name": "用户辩手",
                "side": "affirmative",
                "content": "字母字母字母字母字母字母",
            },
        )
    assert bad.status_code == 200

    negative_view = await client.get(f"/api/debates/{debate_id}?viewer_side=negative")
    assert negative_view.status_code == 200
    negative_text = "\n".join(message["content"] for message in negative_view.json()["messages"])
    assert "字母字母" not in negative_text

    affirmative_view = await client.get(f"/api/debates/{debate_id}?viewer_side=affirmative")
    assert affirmative_view.status_code == 200
    affirmative_messages = affirmative_view.json()["messages"]
    assert any(m.get("speech_flag") == "inappropriate" for m in affirmative_messages)


@pytest.mark.asyncio
async def test_admin_overview_and_list(client: AsyncClient) -> None:
    await client.post("/api/debates", json={"topic": "管理页测试 A", "mode": "ai_autonomous"})
    await client.post("/api/debates", json={"topic": "管理页测试 B", "mode": "ai_autonomous"})

    overview = await client.get("/api/admin/overview")
    assert overview.status_code == 200
    ov = overview.json()
    assert ov["debate_counts"]["total"] >= 2
    assert "active_runners" in ov

    listing = await client.get("/api/admin/debates?limit=10")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) >= 2
    assert all("topic" in item and "message_count" in item for item in items)


@pytest.mark.asyncio
async def test_admin_detail_and_resume_controls(client: AsyncClient) -> None:
    create = await client.post(
        "/api/debates",
        json={"topic": "控制测试", "mode": "ai_autonomous", "schedule_template": "formal_4v4"},
    )
    debate_id = create.json()["id"]

    detail = await client.get(f"/api/admin/debates/{debate_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["summary"]["id"] == debate_id
    assert "llm_stats" in body
    assert "diagnostics" in body

    stop = await client.post(f"/api/admin/debates/{debate_id}/stop-auto")
    assert stop.status_code == 200

    get_after = await client.get(f"/api/debates/{debate_id}")
    assert get_after.json()["auto_running"] is False

    resume = await client.post(f"/api/admin/debates/{debate_id}/resume-auto")
    assert resume.status_code == 200
    assert resume.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_export_markdown(client: AsyncClient) -> None:
    create = await client.post("/api/debates", json={"topic": "导出测试", "mode": "ai_autonomous"})
    debate_id = create.json()["id"]
    export = await client.get(f"/api/debates/{debate_id}/export.md")
    assert export.status_code == 200
    assert "导出测试" in export.text
    assert "# 辩论训练复盘报告" in export.text
    assert "## 比赛设置" in export.text
    assert "## 双方阵容" in export.text
    assert "## 赛程摘要" in export.text
    assert "## 公开发言" in export.text or "## 发言记录" in export.text

    pdf = await client.get(f"/api/debates/{debate_id}/export.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_confidence_monitor_status_and_toggle(client: AsyncClient) -> None:
    status = await client.get("/api/confidence-monitor/status")
    assert status.status_code == 200
    body = status.json()
    assert "running" in body
    assert "available" in body
    assert "missing_dependencies" in body

    off = await client.post("/api/confidence-monitor/toggle", json={"enabled": False})
    assert off.status_code == 200
    assert off.json()["running"] is False

    metrics = await client.get("/api/confidence-monitor/metrics")
    assert metrics.status_code == 200
    assert "metrics" in metrics.json()

    report = await client.post("/api/confidence-monitor/report", json={"max_samples": 120})
    assert report.status_code == 200
    assert "llm_report" in report.json()
