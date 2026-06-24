from __future__ import annotations

from app.core.time_utils import utc_now
from app.models import DebateMessage, DebateState, OnlineParticipant, UserMessageCreate, build_schedule_status
from app.services.argument_bank import add_message_arguments_to_bank_with_ai_titles
from app.services.camera_speech_scoring import apply_camera_speech_score
from app.services.debate_mode import (
    is_user_team_discussion_segment,
    next_online_participant_for_team_discussion,
    participant_speaker_id,
    user_speaker_id,
)
from app.services.debate_schedule import advance_schedule
from app.services.rag import retrieve_sources
from app.services.speech_timeout import apply_timeout_penalty_if_needed, clear_user_wait, mark_user_wait_start
from app.services.user_message_scoring import score_user_public_message
from app.services.user_speech_judge import UserSpeechReview


def speaker_id_for_user_message(
    debate: DebateState,
    participant: OnlineParticipant | None,
    payload: UserMessageCreate,
) -> str:
    if participant is not None:
        return participant_speaker_id(participant) or payload.speaker_id
    return user_speaker_id(debate) or payload.speaker_id


def build_user_message(
    debate: DebateState,
    payload: UserMessageCreate,
    participant: OnlineParticipant | None,
    review: UserSpeechReview,
) -> DebateMessage:
    sources = retrieve_sources(debate.topic, payload.content, debate_id=debate.id) if review.acceptable else []
    return DebateMessage(
        debate_id=debate.id,
        speaker_id=speaker_id_for_user_message(debate, participant, payload),
        speaker_name=payload.speaker_name,
        side=payload.side,
        content=payload.content,
        phase=debate.phase,
        segment_label=debate.segment_label,
        sources=sources[:2] if review.acceptable else [],
        speech_flag="ok" if review.acceptable else "inappropriate",
        review_reason=(review.reason or "发言不符合赛制要求") if not review.acceptable else None,
    )


def apply_user_message_scoring(
    debate: DebateState,
    message: DebateMessage,
    review: UserSpeechReview,
    *,
    public_debate: bool,
    camera_status=None,
) -> None:
    if review.acceptable:
        if public_debate:
            score_user_public_message(debate, message, message.sources)
    else:
        reason = review.reason or "发言不符合赛制要求"
        if not public_debate:
            message.score_reason = f"队内讨论质量不佳：{reason}"
        else:
            penalty = review.penalty if review.penalty > 0 else 0.5
            debate.score[message.side] = debate.score.get(message.side, 0) - penalty
            message.score_delta = -round(penalty, 2)
            message.score_reason = f"发言不当已记录并扣分：{reason} -{penalty:.2f}"

    timeout_delta, timeout_reason = (
        apply_timeout_penalty_if_needed(debate, message.side) if public_debate else (0.0, "")
    )
    if timeout_delta:
        message.score_delta = round((message.score_delta or 0.0) + timeout_delta, 2)
        message.score_reason = "；".join(part for part in [message.score_reason, timeout_reason] if part)

    if public_debate and camera_status is not None and camera_status.running and camera_status.latest_sample:
        camera_delta, camera_reason = apply_camera_speech_score(
            debate,
            message.side,
            camera_status.session_log_path,
            since_ts=camera_status.session_started_at or None,
        )
        if camera_delta:
            message.score_delta = round((message.score_delta or 0.0) + camera_delta, 2)
            message.score_reason = "；".join(part for part in [message.score_reason, camera_reason] if part)


def advance_after_user_message(debate: DebateState, *, internal: bool) -> None:
    debate.awaiting_user = False
    clear_user_wait(debate)
    debate.user_draft = ""
    debate.updated_at = utc_now()
    debate.turn_index += 1

    if internal and is_user_team_discussion_segment(debate):
        waiting_team_participant = next_online_participant_for_team_discussion(debate)
        if waiting_team_participant is not None:
            next_speaker_id = participant_speaker_id(waiting_team_participant)
            if next_speaker_id:
                debate.active_speaker_id = next_speaker_id
            debate.awaiting_user = True
            mark_user_wait_start(debate)
        else:
            debate.awaiting_user = False
            clear_user_wait(debate)
        return

    advance_schedule(debate)
    debate.schedule = build_schedule_status(debate.schedule_index, debate.schedule_template)


async def accept_user_message(
    debate: DebateState,
    payload: UserMessageCreate,
    participant: OnlineParticipant | None,
    *,
    review: UserSpeechReview,
    public_debate: bool,
    internal: bool,
    camera_status=None,
) -> DebateState:
    message = build_user_message(debate, payload, participant, review)
    apply_user_message_scoring(
        debate,
        message,
        review,
        public_debate=public_debate,
        camera_status=camera_status,
    )
    debate.messages.append(message)
    await add_message_arguments_to_bank_with_ai_titles(debate, message)
    advance_after_user_message(debate, internal=internal)
    return debate
