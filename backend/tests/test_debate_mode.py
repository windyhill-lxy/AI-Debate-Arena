from app.models import (
    DebateMode,
    DebateState,
    DebateTiming,
    DebateVisibility,
    OnlineParticipant,
    default_agents,
    workflow_template,
)
from app.services.debate_mode import is_user_task_assign_segment, needs_user_turn, user_speaker_id
from app.services.debate_schedule import apply_segment, get_segment, init_schedule


def _debate(mode: DebateMode) -> DebateState:
    return DebateState(
        topic="测试辩题",
        mode=mode,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
    )


def test_user_speaker_id() -> None:
    aff = _debate(DebateMode.user_affirmative)
    neg = _debate(DebateMode.user_negative)
    auto = _debate(DebateMode.ai_autonomous)
    assert user_speaker_id(aff) == "aff_1"
    assert user_speaker_id(neg) == "neg_1"
    assert user_speaker_id(auto) is None


def test_user_speaker_id_supports_any_debater_seat() -> None:
    aff_three = _debate(DebateMode.user_affirmative)
    aff_three.user_side = "affirmative"
    aff_three.user_position = 3

    neg_four = _debate(DebateMode.user_negative)
    neg_four.user_side = "negative"
    neg_four.user_position = 4

    assert user_speaker_id(aff_three) == "aff_3"
    assert user_speaker_id(neg_four) == "neg_4"


def test_needs_user_turn_supports_internal_team_prep_for_user_side() -> None:
    debate = _debate(DebateMode.user_affirmative)
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "opening_task_assign":
            apply_segment(debate, index)
            assert is_user_task_assign_segment(debate) is True
            assert needs_user_turn(debate) is True
            break

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is True
            break

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "neg_opening_discussion":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is False
            break

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_1":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is True
            break

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.speaker_side == "affirmative" and segment.speaker_position == 2:
            apply_segment(debate, index)
            assert needs_user_turn(debate) is False
            break

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.speaker_side == "judge":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is False
            break


def test_needs_user_turn_matches_configured_debater_position() -> None:
    debate = _debate(DebateMode.user_affirmative)
    debate.user_side = "affirmative"
    debate.user_position = 3
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.speaker_side == "affirmative" and segment.speaker_position == 3:
            apply_segment(debate, index)
            assert needs_user_turn(debate) is True
            break
    else:
        raise AssertionError("missing affirmative third debater segment in schedule")

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.speaker_side == "affirmative" and segment.speaker_position == 1:
            apply_segment(debate, index)
            assert needs_user_turn(debate) is False
            break
    else:
        raise AssertionError("missing affirmative first debater segment in schedule")


def test_ai_autonomous_never_needs_user() -> None:
    debate = _debate(DebateMode.ai_autonomous)
    init_schedule(debate)
    for index in range(5):
        apply_segment(debate, index)
        assert needs_user_turn(debate) is False


def test_online_match_team_discussion_does_not_need_user_turn() -> None:
    debate = _debate(DebateMode.online_match)
    init_schedule(debate)
    debate.participants.append(
        OnlineParticipant(name="正方一辩", side="affirmative", position=1, connected=True),
    )

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "opening_task_assign":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is True
            break
    else:
        raise AssertionError("missing opening_task_assign segment")

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            assert needs_user_turn(debate) is False
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            debate.messages.append(
                __import__("app.models", fromlist=["DebateMessage"]).DebateMessage(
                    debate_id=debate.id,
                    speaker_id="aff_1",
                    speaker_name="正方一辩",
                    side="affirmative",
                    content="用户队内发言",
                    phase=debate.phase,
                    segment_label=debate.segment_label,
                    speech_flag="ok",
                )
            )
            assert needs_user_turn(debate) is False
            break
