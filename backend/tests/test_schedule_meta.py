from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.debate_schedule import advance_schedule, agent_id, apply_segment, get_segment, init_schedule
from app.services.debate_schedule_meta import is_procedural_segment, schedule_progress
from app.services.schedule_config import load_schedule


def _debate() -> DebateState:
    return DebateState(
        topic="测试",
        mode=DebateMode.ai_autonomous,
        visibility=DebateVisibility.context,
        timing=DebateTiming.limited,
        turn_seconds=60,
        format="formal",
        agents=default_agents(),
        workflow=workflow_template(),
        team_discussion_enabled=True,
        rag_review_mode="full",
    )


def test_pre_match_opening_is_not_procedural() -> None:
    debate = _debate()
    init_schedule(debate)
    assert is_procedural_segment(debate) is False


def test_judge_rag_step_is_procedural() -> None:
    debate = _debate()
    init_schedule(debate)
    for index in range(120):
        seg = get_segment(debate, index)
        if seg and "RAG检索" in (seg.label or "") and seg.speaker_side == "judge":
            apply_segment(debate, index)
            assert is_procedural_segment(debate) is True
            break


def test_schedule_progress() -> None:
    debate = _debate()
    init_schedule(debate)
    current, total = schedule_progress(debate)
    assert current == 1
    assert total > 10


def test_free_debate_alternates_sides() -> None:
    debate = _debate()
    for index in range(200):
        segment = get_segment(debate, index)
        if segment and segment.id == "free_debate_pool":
            apply_segment(debate, index)
            debate.free_aff_remaining_sec = 240
            debate.free_neg_remaining_sec = 240
            debate.free_turn_counter = 0
            break
    else:
        raise AssertionError("free_debate_pool segment not found")

    assert debate.active_speaker_id == "aff_1"
    assert advance_schedule(debate) is True
    assert debate.active_speaker_id.startswith("neg_")
    assert "反方" in debate.segment_label

    debate.active_speaker_id = debate.active_speaker_id  # simulate just spoke
    assert advance_schedule(debate) is True
    assert debate.active_speaker_id.startswith("aff_")
    assert "正方" in debate.segment_label

    debate.active_speaker_id = debate.active_speaker_id
    assert advance_schedule(debate) is True
    assert debate.active_speaker_id.startswith("neg_")


def test_formal_4v4_core_public_flow_matches_required_format() -> None:
    schedule = load_schedule("formal_4v4")
    core_phases = {
        "opening_statement",
        "rebuttal",
        "cross_examination",
        "segment_summary",
        "free_debate",
        "closing",
    }
    core = [
        (segment.id, segment.phase, agent_id(segment.speaker_side, segment.speaker_position), segment.seconds)
        for segment in schedule
        if segment.phase in core_phases and segment.speaker_side in {"affirmative", "negative"}
    ]

    assert core == [
        ("aff_opening_1", "opening_statement", "aff_1", 180),
        ("neg_opening_1", "opening_statement", "neg_1", 180),
        ("neg_rebuttal_2", "rebuttal", "neg_2", 120),
        ("aff_rebuttal_2", "rebuttal", "aff_2", 120),
        ("aff_cross_q_neg1", "cross_examination", "aff_3", 15),
        ("neg1_cross_answer", "cross_examination", "neg_1", 30),
        ("aff_cross_q_neg2", "cross_examination", "aff_3", 15),
        ("neg2_cross_answer", "cross_examination", "neg_2", 30),
        ("aff_cross_q_neg4", "cross_examination", "aff_3", 15),
        ("neg4_cross_answer", "cross_examination", "neg_4", 30),
        ("neg_cross_q_aff1", "cross_examination", "neg_3", 15),
        ("aff1_cross_answer", "cross_examination", "aff_1", 30),
        ("neg_cross_q_aff2", "cross_examination", "neg_3", 15),
        ("aff2_cross_answer", "cross_examination", "aff_2", 30),
        ("neg_cross_q_aff4", "cross_examination", "neg_3", 15),
        ("aff4_cross_answer", "cross_examination", "aff_4", 30),
        ("aff_summary_3", "segment_summary", "aff_3", 90),
        ("neg_summary_3", "segment_summary", "neg_3", 90),
        ("free_debate_pool", "free_debate", "aff_1", 30),
        ("closing_neg4", "closing", "neg_4", 180),
        ("closing_aff4", "closing", "aff_4", 180),
    ]


def test_formal_4v4_cross_examination_rules_name_question_and_answer_targets() -> None:
    segments = {segment.id: segment for segment in load_schedule("formal_4v4")}

    assert "提问方：正方三辩" in segments["aff_cross_q_neg1"].rules
    assert "回答方：反方一辩" in segments["aff_cross_q_neg1"].rules
    assert "回答方：反方二辩" in segments["neg2_cross_answer"].rules
    assert "回答方：反方四辩" in segments["neg4_cross_answer"].rules
    assert "提问方：反方三辩" in segments["neg_cross_q_aff1"].rules
    assert "回答方：正方一辩" in segments["neg_cross_q_aff1"].rules
    assert "回答方：正方二辩" in segments["aff2_cross_answer"].rules
    assert "回答方：正方四辩" in segments["aff4_cross_answer"].rules


def test_fast_room_skips_team_discussion_when_disabled() -> None:
    debate = _debate()
    debate.team_discussion_enabled = False
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "evidence_split":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("evidence_split segment not found")

    assert get_segment(debate, debate.schedule_index).id == "aff_opening_1"


def test_fast_room_skips_all_internal_discussion_setup_when_disabled() -> None:
    debate = _debate()
    debate.team_discussion_enabled = False
    init_schedule(debate)

    visited: list[str] = []
    for _ in range(20):
        current = get_segment(debate, debate.schedule_index)
        if current:
            visited.append(current.id)
        if current and current.id == "aff_opening_1":
            break
        assert advance_schedule(debate) is True

    assert "opening_task_assign" not in visited
    assert "neg_opening_task_assign" not in visited
    assert "aff_opening_discussion" not in visited
    assert "neg_opening_discussion" not in visited
    assert visited[-1] == "aff_opening_1"


def test_essential_rag_mode_skips_public_review_segments() -> None:
    debate = _debate()
    debate.rag_review_mode = "essential"
    init_schedule(debate)

    for index in range(120):
        segment = get_segment(debate, index)
        if segment and segment.id == "aff_opening_1":
            apply_segment(debate, index)
            break
    else:
        raise AssertionError("aff_opening_1 segment not found")

    assert advance_schedule(debate) is True
    assert get_segment(debate, debate.schedule_index).id == "neg_opening_1"
