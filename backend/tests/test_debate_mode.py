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
from app.services.debate_mode import (
    is_user_task_assign_segment,
    needs_user_turn,
    prepare_next_online_user_turn,
    user_speaker_id,
)
from app.services.debate_schedule import apply_segment, get_segment, init_schedule
from app.models import build_schedule_status


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
        team_discussion_enabled=True,
        rag_review_mode="full",
    )


def _fill_opening_argument_bank(debate: DebateState) -> None:
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


def test_opening_evidence_bank_runs_before_first_debater_task_assignment() -> None:
    ids = [item.id for item in build_schedule_status(0, "formal_4v4")]

    assert ids.index("opening_evidence_bank") < ids.index("opening_task_assign")
    assert ids.index("opening_evidence_bank") < ids.index("neg_opening_task_assign")


def test_workflow_template_places_opening_evidence_before_task_assignment() -> None:
    ids = [node.id for node in workflow_template()]

    assert ids.index("opening_evidence_bank") < ids.index("opening_task_assign")


def test_formal_schedule_removes_free_and_closing_team_discussions() -> None:
    ids = [item.id for item in build_schedule_status(0, "formal_4v4")]

    assert "aff_free_team_discussion" not in ids
    assert "neg_free_team_discussion" not in ids
    assert "aff_closing_discussion" not in ids
    assert "neg_closing_discussion" not in ids
    assert ids.index("free_ready") < ids.index("free_debate_pool")
    assert ids.index("closing_frame") < ids.index("closing_neg4")


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
            assert needs_user_turn(debate) is False
            _fill_opening_argument_bank(debate)
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


def test_online_match_team_discussion_waits_for_connected_debater() -> None:
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
            _fill_opening_argument_bank(debate)
            assert needs_user_turn(debate) is True
            assert debate.active_speaker_id == "aff_1"
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            _fill_opening_argument_bank(debate)
            debate.messages.append(
                DebateMessage(
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


def test_online_match_team_discussion_waits_each_connected_debater_once() -> None:
    debate = _debate(DebateMode.online_match)
    init_schedule(debate)
    debate.participants.append(OnlineParticipant(name="aff one", side="affirmative", position=1, connected=True))
    debate.participants.append(OnlineParticipant(name="aff two", side="affirmative", position=2, connected=True))

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            _fill_opening_argument_bank(debate)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    assert needs_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_1"
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="aff one",
            side="affirmative",
            content="first user internal speech",
            phase=debate.phase,
            segment_label=debate.segment_label,
            speech_flag="ok",
        )
    )
    assert needs_user_turn(debate) is True
    assert prepare_next_online_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_2"
    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_2",
            speaker_name="aff two",
            side="affirmative",
            content="second user internal speech",
            phase=debate.phase,
            segment_label=debate.segment_label,
            speech_flag="ok",
        )
    )
    assert needs_user_turn(debate) is False


def test_online_match_opening_discussion_skips_first_debater_after_task_assign() -> None:
    debate = _debate(DebateMode.online_match)
    init_schedule(debate)
    debate.participants.append(OnlineParticipant(name="正方一辩", side="affirmative", position=1, connected=True))
    debate.participants.append(OnlineParticipant(name="正方二辩", side="affirmative", position=2, connected=True))

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            _fill_opening_argument_bank(debate)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="正方一辩",
            side="affirmative",
            content="任务分配已经发言。",
            phase=debate.phase,
            segment_label="立论前准备 · 一辩任务分配",
            speech_flag="ok",
        )
    )

    assert needs_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_1"
    assert prepare_next_online_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_2"


def test_needs_user_turn_is_readonly_for_online_team_discussion() -> None:
    debate = _debate(DebateMode.online_match)
    init_schedule(debate)
    debate.participants.append(OnlineParticipant(name="正方二辩", side="affirmative", position=2, connected=True))

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            _fill_opening_argument_bank(debate)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="正方一辩",
            side="affirmative",
            content="任务分配已经发言。",
            phase=debate.phase,
            segment_label="立论前准备 · 一辩任务分配",
            speech_flag="ok",
        )
    )

    assert debate.active_speaker_id == "aff_1"
    assert needs_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_1"
    assert prepare_next_online_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_2"


def test_online_match_team_discussion_waits_for_claimed_human_seat_even_if_socket_is_between_polls() -> None:
    from app.services.debate_mode import next_online_participant_for_team_discussion

    debate = _debate(DebateMode.online_match)
    init_schedule(debate)
    debate.participants.append(OnlineParticipant(name="正方二辩", side="affirmative", position=2, connected=False))

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            _fill_opening_argument_bank(debate)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    debate.messages.append(
        DebateMessage(
            debate_id=debate.id,
            speaker_id="aff_1",
            speaker_name="正方一辩",
            side="affirmative",
            content="任务分配已经发言。",
            phase=debate.phase,
            segment_label="立论前准备 · 一辩任务分配",
            speech_flag="ok",
        )
    )

    waiting = next_online_participant_for_team_discussion(debate)
    assert waiting is not None
    assert waiting.position == 2
    assert needs_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_1"
    assert prepare_next_online_user_turn(debate) is True
    assert debate.active_speaker_id == "aff_2"


def test_opening_team_discussion_waits_for_argument_bank_before_user_turn() -> None:
    debate = _debate(DebateMode.user_affirmative)
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    assert needs_user_turn(debate) is False
    _fill_opening_argument_bank(debate)
    assert needs_user_turn(debate) is True


def test_opening_team_discussion_waits_for_evidence_flow_not_full_target() -> None:
    debate = _debate(DebateMode.user_affirmative)
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_discussion":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("missing aff_opening_discussion segment")

    debate.opening_evidence_completed = True
    debate.argument_bank_locked = True
    debate.argument_bank["affirmative"] = debate.argument_bank["affirmative"][:0]
    debate.argument_bank["negative"] = debate.argument_bank["negative"][:0]

    assert needs_user_turn(debate) is True
