from app.models import DebateMode, DebateState, DebateTiming, DebateVisibility, default_agents, workflow_template
from app.services.debate_schedule import advance_schedule, apply_segment, get_segment, init_schedule
from app.services.debate_schedule_meta import is_procedural_segment, schedule_progress


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
