import pytest

from app.models import (
    ArgumentBankItem,
    DebateMode,
    DebateMessage,
    DebateState,
    DebateTiming,
    DebateVisibility,
    OnlineParticipant,
    default_agents,
    workflow_template,
)
from app.services.debate_schedule import apply_segment, get_segment, init_schedule


def _debate() -> DebateState:
    debate = DebateState(
        topic="队内讨论模块测试",
        mode=DebateMode.online_match,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
    )
    init_schedule(debate)
    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing affirmative opening discussion segment")
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = [
        ArgumentBankItem(
            id=f"AFF-{index}",
            side="affirmative",
            title=f"正方论据{index}",
            claim=f"2024年机构报告显示正方论据{index}。",
        )
        for index in range(1, 11)
    ]
    return debate


def test_team_discussion_speakers_skip_connected_human_seats() -> None:
    from app.services.team_discussion import team_discussion_speakers

    debate = _debate()
    debate.participants.append(
        OnlineParticipant(name="真人二辩", side="affirmative", position=2, connected=True)
    )
    active = next(agent for agent in debate.agents if agent.id == "aff_1")

    speakers = team_discussion_speakers(debate, active)

    assert [speaker.id for speaker in speakers] == ["aff_1", "aff_3", "aff_4"]


def test_team_discussion_speakers_skip_claimed_human_seats_and_prior_task_assign_first_debater() -> None:
    from app.services.team_discussion import team_discussion_speakers

    debate = _debate()
    debate.participants.append(
        OnlineParticipant(name="真人二辩", side="affirmative", position=2, connected=False)
    )
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="正方一辩",
            side="affirmative",
            content="我完成任务分配。",
            phase=debate.phase,
            segment_label="立论前准备 · 一辩任务分配",
            speech_flag="ok",
        )
    )
    active = next(agent for agent in debate.agents if agent.id == "aff_1")

    speakers = team_discussion_speakers(debate, active)

    assert [speaker.id for speaker in speakers] == ["aff_3", "aff_4"]


@pytest.mark.asyncio
async def test_generate_team_discussion_draft_adds_argument_id_on_fallback() -> None:
    from app.services.llm import DeepSeekError
    from app.services.team_discussion import TeamDiscussionContext, generate_team_discussion_draft

    debate = _debate()
    teammate = next(agent for agent in debate.agents if agent.id == "aff_3")

    async def unavailable_llm(*_args, **_kwargs):
        raise DeepSeekError("offline")

    draft = await generate_team_discussion_draft(
        debate,
        TeamDiscussionContext(stance_action="队内讨论", strategy="先事实后标准", sources=[]),
        teammate,
        chat_completion_fn=unavailable_llm,
    )

    assert draft.agent.id == "aff_3"
    assert "[AFF-" in draft.content
