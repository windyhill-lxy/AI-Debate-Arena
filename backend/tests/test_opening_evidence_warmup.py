from __future__ import annotations

import pytest

from app.models import (
    ArgumentBankItem,
    DebateMode,
    DebateState,
    DebateTiming,
    DebateVisibility,
    OnlineParticipant,
    default_agents,
    workflow_template,
)
from app.services.debate_schedule import init_schedule


def _debate(topic: str = "旧辩题") -> DebateState:
    debate = DebateState(
        topic=topic,
        mode=DebateMode.online_match,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
    )
    init_schedule(debate)
    return debate


def _warm_bank() -> dict[str, list[ArgumentBankItem]]:
    return {
        "affirmative": [
            ArgumentBankItem(id=f"AFF-{index}", side="affirmative", title=f"正方事实{index}", claim=f"2024年正方事实{index}。")
            for index in range(1, 11)
        ],
        "negative": [
            ArgumentBankItem(id=f"NEG-{index}", side="negative", title=f"反方事实{index}", claim=f"2024年反方事实{index}。")
            for index in range(1, 11)
        ],
    }


@pytest.mark.asyncio
async def test_opening_evidence_prepare_endpoint_starts_warmup(client, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.api.debates.warm_opening_evidence",
        lambda debate: calls.append((debate.id, debate.topic)),
    )

    response = await client.post(
        "/api/debates/opening-evidence-prep",
        json={"topic": "提前搜集测试", "schedule_template": "formal_4v4"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prep_id"]
    assert body["topic"] == "提前搜集测试"
    assert calls == [(body["prep_id"], "提前搜集测试")]


@pytest.mark.asyncio
async def test_create_debate_merges_matching_opening_evidence_prep(client, monkeypatch) -> None:
    from app.db.mongo import save_debate

    prep = _debate("复用准备论据")
    prep.argument_bank = _warm_bank()
    prep.argument_bank_locked = True
    await save_debate(prep.model_dump(mode="json"))

    monkeypatch.setattr("app.api.debates.warm_opening_evidence", lambda _debate: None)

    response = await client.post(
        "/api/debates",
        json={
            "topic": "复用准备论据",
            "mode": "ai_autonomous",
            "schedule_template": "formal_4v4",
            "opening_evidence_prep_id": prep.id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["argument_bank"]["affirmative"][0]["id"] == "AFF-1"
    assert body["argument_bank"]["negative"][0]["id"] == "NEG-1"


@pytest.mark.asyncio
async def test_opening_evidence_prepare_cancel_endpoint_cancels_warmup(client, monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "app.api.debates.cancel_opening_evidence_warmup",
        lambda prep_id: calls.append(prep_id),
    )

    response = await client.delete("/api/debates/opening-evidence-prep/prep-123")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert calls == ["prep-123"]


@pytest.mark.asyncio
async def test_opening_evidence_warmup_ignores_stale_topic(monkeypatch) -> None:
    from app.db.mongo import get_debate, save_debate
    from app.services import opening_evidence_warmup

    stale = _debate("旧辩题")
    await save_debate(stale.model_dump(mode="json"))

    async def fake_ensure(warmup_state: DebateState, **_kwargs):
        warmup_state.argument_bank = _warm_bank()
        warmup_state.argument_bank_locked = True
        return opening_evidence_warmup.OpeningEvidenceWarmupResult(ready=True)

    monkeypatch.setattr(opening_evidence_warmup, "ensure_opening_argument_bank", fake_ensure)

    await save_debate(stale.model_copy(update={"topic": "新辩题"}).model_dump(mode="json"))
    ready_calls: list[str] = []
    await opening_evidence_warmup.run_opening_evidence_warmup_once(
        stale.id,
        "旧辩题",
        on_ready=ready_calls.append,
    )

    latest = DebateState.model_validate(await get_debate(stale.id))
    assert latest.topic == "新辩题"
    assert latest.argument_bank["affirmative"] == []
    assert latest.argument_bank["negative"] == []
    assert latest.argument_bank_locked is False
    assert ready_calls == []


@pytest.mark.asyncio
async def test_opening_evidence_warmup_merges_into_latest_state_without_overwriting_participants(monkeypatch) -> None:
    from app.db.mongo import get_debate, save_debate
    from app.services import opening_evidence_warmup

    debate = _debate("预热合并测试")
    await save_debate(debate.model_dump(mode="json"))

    async def fake_ensure(warmup_state: DebateState, **_kwargs):
        warmup_state.argument_bank = _warm_bank()
        warmup_state.argument_bank_locked = True
        latest = warmup_state.model_copy(deep=True)
        latest.argument_bank = {"affirmative": [], "negative": []}
        latest.argument_bank_locked = False
        latest.participants.append(
            OnlineParticipant(id="p1", name="正方一辩", side="affirmative", position=1)
        )
        await save_debate(latest.model_dump(mode="json"))
        return opening_evidence_warmup.OpeningEvidenceWarmupResult(ready=True)

    monkeypatch.setattr(opening_evidence_warmup, "ensure_opening_argument_bank", fake_ensure)

    await opening_evidence_warmup.run_opening_evidence_warmup_once(debate.id, debate.topic)

    latest = DebateState.model_validate(await get_debate(debate.id))
    assert [participant.id for participant in latest.participants] == ["p1"]
    assert latest.argument_bank["affirmative"][0].id == "AFF-1"
    assert latest.argument_bank["negative"][0].id == "NEG-1"


@pytest.mark.asyncio
async def test_opening_evidence_warmup_resumes_when_bank_becomes_ready(monkeypatch) -> None:
    from app.db.mongo import save_debate
    from app.services import opening_evidence_warmup

    debate = _debate("预热恢复测试")
    await save_debate(debate.model_dump(mode="json"))

    async def fake_ensure(warmup_state: DebateState, **_kwargs):
        warmup_state.argument_bank = _warm_bank()
        warmup_state.argument_bank_locked = True
        return opening_evidence_warmup.OpeningEvidenceWarmupResult(ready=True)

    ready_calls: list[str] = []
    monkeypatch.setattr(opening_evidence_warmup, "ensure_opening_argument_bank", fake_ensure)

    result = await opening_evidence_warmup.run_opening_evidence_warmup_once(
        debate.id,
        debate.topic,
        on_ready=ready_calls.append,
    )

    assert result.ready is True
    assert ready_calls == [debate.id]
