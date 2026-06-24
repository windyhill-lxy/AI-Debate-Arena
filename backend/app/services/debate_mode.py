from app.models import DebateMode, DebateState, OnlineParticipant
from app.services.argument_bank import opening_argument_bank_ready
from app.services.debate_schedule import agent_id, get_segment


def _side_from_speaker_id(speaker_id: str | None) -> str | None:
    if not speaker_id:
        return None
    if speaker_id.startswith("aff_"):
        return "affirmative"
    if speaker_id.startswith("neg_"):
        return "negative"
    return None


def user_side_for_mode(mode: DebateMode) -> str | None:
    if mode == DebateMode.user_affirmative:
        return "affirmative"
    if mode == DebateMode.user_negative:
        return "negative"
    return None


def debate_user_side(debate: DebateState) -> str | None:
    return debate.user_side or user_side_for_mode(debate.mode)


def debate_user_position(debate: DebateState) -> int:
    return debate.user_position if debate.user_position in {1, 2, 3, 4} else 1


def participant_speaker_id(participant: OnlineParticipant) -> str | None:
    if participant.side not in {"affirmative", "negative"} or not participant.position:
        return None
    return agent_id(participant.side, participant.position)


def participant_for_active_speaker(debate: DebateState) -> OnlineParticipant | None:
    if debate.mode != DebateMode.online_match:
        return None
    for participant in debate.participants:
        if participant.connected and participant_speaker_id(participant) == debate.active_speaker_id:
            return participant
    return None


def _position_from_speaker_id(speaker_id: str | None, side: str) -> int | None:
    prefix = "aff_" if side == "affirmative" else "neg_"
    speaker = speaker_id or ""
    if not speaker.startswith(prefix):
        return None
    try:
        position = int(speaker.split("_", 1)[1])
    except (IndexError, ValueError):
        return None
    return position if position in {1, 2, 3, 4} else None


def _positions_spoken_in_current_segment(debate: DebateState, side: str) -> set[int]:
    positions: set[int] = set()
    label = debate.segment_label or ""
    for message in debate.messages:
        if message.side != side or message.segment_label != label:
            continue
        position = _position_from_speaker_id(message.speaker_id, side)
        if position is not None:
            positions.add(position)
    return positions


def _positions_spoken_in_current_team_prep(debate: DebateState, side: str) -> set[int]:
    positions = _positions_spoken_in_current_segment(debate, side)
    if debate.phase == "opening_prep" and "队内讨论" in (debate.segment_label or ""):
        task_label = "反方一辩任务分配" if side == "negative" else "一辩任务分配"
        for message in debate.messages:
            if message.side != side or task_label not in (message.segment_label or ""):
                continue
            position = _position_from_speaker_id(message.speaker_id, side)
            if position is not None:
                positions.add(position)
    return positions


def next_online_participant_for_team_discussion(debate: DebateState) -> OnlineParticipant | None:
    if debate.mode != DebateMode.online_match or not is_user_team_discussion_segment(debate):
        return None
    team_side = _segment_side_for_team_discussion(debate)
    if team_side not in {"affirmative", "negative"}:
        return None
    spoken = _positions_spoken_in_current_team_prep(debate, team_side)
    candidates = [
        p
        for p in debate.participants
        if p.side == team_side
        and p.position in {1, 2, 3, 4}
        and p.position not in spoken
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.position or 9)[0]


def online_team_discussion_has_waiting_participant(debate: DebateState) -> bool:
    return next_online_participant_for_team_discussion(debate) is not None


def user_speaker_id(debate: DebateState) -> str | None:
    """人机模式下用户对应的辩手席位 ID（aff_N / neg_N）。"""
    side = debate_user_side(debate)
    if not side:
        return None
    return agent_id(side, debate_user_position(debate))


def is_user_task_assign_segment(debate: DebateState) -> bool:
    """准备环节中仅「一辩任务分配」需要用户亲自发言。"""
    label = debate.segment_label or ""
    if "任务分配" in label:
        return True
    segment = get_segment(debate, debate.schedule_index)
    return bool(segment and segment.id in {"opening_task_assign", "neg_opening_task_assign"})


def is_user_team_discussion_segment(debate: DebateState) -> bool:
    label = debate.segment_label or ""
    return debate.phase in {"opening_prep", "free_prep", "closing_prep"} and "队内讨论" in label


def opening_team_discussion_ready(debate: DebateState) -> bool:
    if debate.phase != "opening_prep" or not is_user_team_discussion_segment(debate):
        return True
    return opening_argument_bank_ready(debate)


def _user_spoke_in_current_segment(debate: DebateState) -> bool:
    user_id = user_speaker_id(debate)
    if not user_id:
        return False
    label = debate.segment_label or ""
    for msg in debate.messages:
        if msg.segment_label == label and msg.speech_flag is not None:
            return True
    return False


def _segment_side_for_team_discussion(debate: DebateState) -> str | None:
    segment = get_segment(debate, debate.schedule_index)
    if segment and segment.speaker_side in {"affirmative", "negative"}:
        return segment.speaker_side
    label = debate.segment_label or ""
    if "正方" in label:
        return "affirmative"
    if "反方" in label:
        return "negative"
    return None


def user_turn_allowed(debate: DebateState, participant: OnlineParticipant | None = None) -> bool:
    """与 POST /message 校验一致：当前参与者是否允许提交发言。"""
    internal_prep = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
    if internal_prep and not is_user_task_assign_segment(debate) and not is_user_team_discussion_segment(debate):
        return False
    if not opening_team_discussion_ready(debate):
        return False
    if debate.mode == DebateMode.online_match:
        if participant is None:
            return False
        seat_id = participant_speaker_id(participant)
        if not seat_id or seat_id != debate.active_speaker_id:
            return False
        return needs_user_turn(debate) or debate.awaiting_user
    if not needs_user_turn(debate) and not debate.awaiting_user:
        return False
    return True


def user_turn_allowed_readonly(debate: DebateState, participant: OnlineParticipant | None = None) -> bool:
    """只读判断当前参与者是否允许提交发言，不修改 active_speaker_id。"""
    internal_prep = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
    if internal_prep and not is_user_task_assign_segment(debate) and not is_user_team_discussion_segment(debate):
        return False
    if not opening_team_discussion_ready(debate):
        return False
    if debate.mode == DebateMode.online_match:
        if participant is None:
            return False
        seat_id = participant_speaker_id(participant)
        if not seat_id or seat_id != debate.active_speaker_id:
            return False
        return debate.awaiting_user or participant_for_active_speaker(debate) is not None
    if debate.awaiting_user:
        return True
    expected_side = debate_user_side(debate)
    if not expected_side:
        return False
    user_id = user_speaker_id(debate)
    if internal_prep:
        if is_user_task_assign_segment(debate):
            return bool(user_id and debate.active_speaker_id == user_id)
        if is_user_team_discussion_segment(debate):
            team_side = _segment_side_for_team_discussion(debate)
            if not user_id or team_side != expected_side:
                return False
            return not _user_spoke_in_current_segment(debate)
        return False
    return bool(user_id and debate.active_speaker_id == user_id)


def needs_user_turn(debate: DebateState) -> bool:
    internal_team_phase = debate.phase in {"opening_prep", "free_prep", "closing_prep"}
    if debate.mode == DebateMode.online_match:
        if internal_team_phase:
            if is_user_task_assign_segment(debate):
                return participant_for_active_speaker(debate) is not None
            if not opening_team_discussion_ready(debate):
                return False
            participant = next_online_participant_for_team_discussion(debate)
            if participant is not None:
                debate.active_speaker_id = participant_speaker_id(participant) or debate.active_speaker_id
                return True
            return False
        return participant_for_active_speaker(debate) is not None
    expected_side = debate_user_side(debate)
    if not expected_side:
        return False
    user_id = user_speaker_id(debate)
    if internal_team_phase:
        if is_user_task_assign_segment(debate):
            return bool(user_id and debate.active_speaker_id == user_id)
        if is_user_team_discussion_segment(debate):
            if not opening_team_discussion_ready(debate):
                return False
            team_side = _segment_side_for_team_discussion(debate)
            if not user_id or team_side != expected_side:
                return False
            return not _user_spoke_in_current_segment(debate)
        return False
    return bool(user_id and debate.active_speaker_id == user_id)


def peek_next_speaker_id(debate: DebateState) -> str | None:
    next_index = debate.schedule_index + 1
    segment = get_segment(debate, next_index)
    if segment is None:
        return None
    if segment.speaker_side == "judge":
        return "judge"
    return agent_id(segment.speaker_side, segment.speaker_position)
