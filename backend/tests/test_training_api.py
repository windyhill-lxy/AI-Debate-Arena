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


@pytest.mark.asyncio
async def test_opening_training_auto_improve_uses_separate_draft_and_review_calls(client: AsyncClient, monkeypatch) -> None:
    operations: list[str] = []

    async def fake_stream(*_args, **kwargs):
        operations.append(kwargs.get("operation", ""))
        yield "主席、评委，大家好。我方认为人工智能会提升学习能力。第一，AI 能即时反馈。第二，AI 能提供材料。第三，AI 能帮助复盘。因此我方认为它有助于学习。"

    async def fake_chat_completion(*_args, **kwargs):
        operations.append(kwargs.get("operation", ""))
        return (
            "本轮审核：这篇稿件有基本结构，但还没有达到正式一辩立论标准。"
            "第一，定义只说了学习能力，没有界定综合学习能力的判断标准。"
            "第二，三条论点都偏短，论据缺少具体来源、场景和可核验细节。"
            "第三，结尾没有比较正反双方标准，也没有提前回应反方关于依赖和替代思考的攻击。"
            "下一版应补充清晰定义、三个可验证案例、反方预判和价值收束。"
        )

    monkeypatch.setattr("app.services.training.chat_completion_stream", fake_stream)
    monkeypatch.setattr("app.services.training.chat_completion", fake_chat_completion)

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
    assert "opening_training_auto_improve_stream" in operations
    assert "opening_training_review" in operations
    assert "本轮审核" in text
    assert len(text[text.find("本轮审核"):]) > 120


@pytest.mark.asyncio
async def test_opening_training_auto_improve_continues_when_reviewer_says_not_ready(client: AsyncClient, monkeypatch) -> None:
    round_no = 0

    async def fake_stream(*_args, **_kwargs):
        nonlocal round_no
        round_no += 1
        yield (
            "主席、评委、对方辩友，大家好。定义上，综合学习能力是理解、迁移和表达能力。"
            "判断标准是学生是否获得稳定训练。第一，AI 能即时反馈并提升效率。"
            "第二，AI 能提供多样材料。第三，AI 能帮助复盘论证。"
            "综上，我方认为 AI 能提升青少年的综合学习能力。"
        )

    async def fake_chat_completion(*_args, **kwargs):
        return (
            "本轮审核：尚未达到正式一辩立论标准。结构虽然完整，但论据仍然空泛，缺少真实案例来源，"
            "也没有回应反方关于依赖和替代思考的攻击。下一轮必须补充可核验事实和更强的标准比较。"
        )

    monkeypatch.setattr("app.services.training.chat_completion_stream", fake_stream)
    monkeypatch.setattr("app.services.training.chat_completion", fake_chat_completion)

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
    assert len(body["rounds"]) == 2
    assert body["passed"] is False


@pytest.mark.asyncio
async def test_opening_training_polish_returns_revised_draft(client: AsyncClient, monkeypatch) -> None:
    async def fake_chat_completion(*_args, **kwargs):
        assert kwargs.get("operation") == "opening_training_polish"
        return "主席、评委、对方辩友，大家好。润色后的立论保留原意，并补强定义、论据和结尾收束。"

    monkeypatch.setattr("app.services.training.chat_completion", fake_chat_completion)
    response = await client.post(
        "/api/debates/opening-training/polish",
        json={
            "topic": "人工智能是否会提升青少年的综合学习能力",
            "side": "affirmative",
            "draft": "我方认为 AI 能提升学习能力。第一，反馈快。第二，资料多。第三，能复盘。",
            "advice": ["补充定义", "补充论据"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["polished_draft"]
    assert "润色后的立论" in body["polished_draft"]
