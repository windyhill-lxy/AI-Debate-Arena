"""按观赛视角构建下发给前端的 debate payload。"""

from __future__ import annotations

from app.models import DebateMessage, DebateMode, DebateState, OnlineParticipant
from app.services.debate_mode import debate_user_side
from app.services.message_visibility import (
    filter_messages_for_viewer,
    is_judge_thought_message,
    is_public_message,
    message_visible_to_side,
)

VIEWER_MODES = frozenset({"context", "realistic", "god", "all_visible", "own_side_only"})
INTERNAL_PREP_PHASES = frozenset({"opening_prep", "free_prep", "closing_prep"})

STREAMING_EVENT_TYPES = frozenset({
    "speech_start",
    "speech_chunk",
    "speech_end",
    "speech_audio_start",
    "speech_audio_progress",
    "speech_audio",
    "speech_audio_error",
})


def normalize_viewer_mode(viewer_mode: str | None) -> str:
    if viewer_mode == "all_visible":
        return "god"
    if viewer_mode == "own_side_only":
        return "realistic"
    if viewer_mode in VIEWER_MODES:
        return viewer_mode
    return "context"


def resolve_viewer_side(
    debate: DebateState,
    *,
    viewer_side: str | None = None,
    participant: OnlineParticipant | None = None,
) -> str | None:
    if viewer_side in {"affirmative", "negative"}:
        return viewer_side
    if participant and participant.side in {"affirmative", "negative"}:
        return participant.side
    if debate.mode in {DebateMode.user_affirmative, DebateMode.user_negative}:
        return debate_user_side(debate)
    return None


def filter_messages_for_viewer_mode(
    messages: list[DebateMessage],
    *,
    viewer_mode: str,
    viewer_side: str | None,
    in_internal_phase: bool,
) -> list[DebateMessage]:
    mode = normalize_viewer_mode(viewer_mode or debate.visibility.value)
    if mode == "god":
        return list(messages)
    if viewer_side:
        if mode == "context":
            visible: list[DebateMessage] = []
            for message in messages:
                if message_visible_to_side(message, viewer_side, in_internal_phase=in_internal_phase):
                    visible.append(message)
                elif is_judge_thought_message(message):
                    visible.append(message)
            return visible
        return filter_messages_for_viewer(messages, viewer_side, in_internal_phase=in_internal_phase)
    return [message for message in messages if is_public_message(message)]


def apply_strategy_field_policy(
    messages: list[DebateMessage],
    viewer_mode: str,
    *,
    viewer_side: str | None = None,
) -> None:
    mode = normalize_viewer_mode(viewer_mode)
    if mode == "god":
        return
    for message in messages:
        if mode == "realistic":
            message.private_thought = None
            message.strategy = None
            continue
        if mode == "context":
            if not viewer_side:
                message.private_thought = None
                message.strategy = None
            elif message.side in {"affirmative", "negative"} and message.side != viewer_side:
                message.private_thought = None
                message.strategy = None


def debate_payload_for_viewer(
    debate: DebateState,
    *,
    viewer_side: str | None = None,
    participant: OnlineParticipant | None = None,
    viewer_mode: str | None = None,
) -> dict:
    mode = normalize_viewer_mode(viewer_mode)
    clone = debate.model_copy(deep=True)
    side = resolve_viewer_side(debate, viewer_side=viewer_side, participant=participant)
    in_internal = debate.phase in INTERNAL_PREP_PHASES
    clone.messages = filter_messages_for_viewer_mode(
        clone.messages,
        viewer_mode=mode,
        viewer_side=side,
        in_internal_phase=in_internal,
    )
    apply_strategy_field_policy(clone.messages, mode, viewer_side=side)
    from app.services.debate_mode import user_turn_allowed

    payload = clone.model_dump(mode="json")
    payload["viewer_mode"] = mode
    payload["user_turn_allowed"] = user_turn_allowed(debate, participant)
    return payload


def streaming_event_visible(
    debate: DebateState,
    payload: dict,
    *,
    viewer_side: str | None,
    viewer_mode: str | None,
) -> bool:
    if payload.get("type") not in STREAMING_EVENT_TYPES:
        return True
    mode = normalize_viewer_mode(viewer_mode)
    if mode == "god":
        return True
    side = payload.get("side")
    if side not in {"affirmative", "negative", "judge", "assistant"}:
        return True
    probe = DebateMessage(
        debate_id=debate.id,
        speaker_id=payload.get("speaker_id") or side,
        speaker_name=payload.get("speaker_name") or "",
        side=side,
        content=payload.get("content") or payload.get("chunk") or "",
        phase=payload.get("phase") or debate.phase,
        segment_label=payload.get("segment_label") or debate.segment_label,
    )
    in_internal = debate.phase in INTERNAL_PREP_PHASES
    if viewer_side:
        if mode == "context" and is_judge_thought_message(probe):
            return True
        return message_visible_to_side(probe, viewer_side, in_internal_phase=in_internal)
    return is_public_message(probe)
