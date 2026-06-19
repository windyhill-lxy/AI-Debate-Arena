import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_free_training_prepare_endpoint_is_removed(client: AsyncClient) -> None:
    response = await client.post("/api/debates/free-training/prepare", json={"topic": "中学生是否应该使用 AI 辅助写作"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_opening_training_analyze_scores_draft_and_reports_rag_checks(client: AsyncClient) -> None:
    response = await client.post(
        "/api/debates/opening-training/analyze",
        json={
            "topic": "人工智能是否会提升青少年的综合学习能力",
            "side": "affirmative",
            "draft": "我方认为会提升。第一，AI 能即时反馈。第二，AI 能提供多样材料。第三，AI 能帮助复盘。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    assert body["side"] == "affirmative"
    assert body["structure"]["has_three_arguments"] is True
    assert "rag_checks" in body
    assert body["revision_advice"]


@pytest.mark.asyncio
async def test_opening_training_auto_improve_returns_dialogue_and_respects_round_limit(client: AsyncClient) -> None:
    response = await client.post(
        "/api/debates/opening-training/auto-improve",
        json={
            "topic": "人工智能是否会提升青少年的综合学习能力",
            "side": "affirmative",
            "max_rounds": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side"] == "affirmative"
    assert 1 <= len(body["rounds"]) <= 2
    assert body["conversation"]
    assert body["conversation"][0]["speaker_name"]
    assert body["conversation"][0]["avatar"]
    assert body["final_draft"]
    assert body["final_score"] < 100


@pytest.mark.asyncio
async def test_opening_training_auto_improve_streams_round_events(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/api/debates/opening-training/auto-improve/stream",
        json={
            "topic": "人工智能是否会提升青少年的综合学习能力",
            "side": "affirmative",
            "max_rounds": 1,
        },
    ) as response:
        body = await response.aread()

    assert response.status_code == 200
    text = body.decode("utf-8")
    assert '"type": "draft"' in text
    assert '"type": "review"' in text
    assert '"type": "done"' in text
